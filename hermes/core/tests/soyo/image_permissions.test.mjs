// SPDX-License-Identifier: MIT
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { SoyoRoleRuntime } from '../../soyo/dsh/host/role-runtime.mjs';
import { sceneImagePaths, imageMayGenerate } from '../../soyo/dsh/host/image-policy.mjs';
const config = { brain_mode:'character-action', admin_ids:['100001'], owner_group_ids:['200001'],
  image_permissions:{enabled:true,allow_group_members:true,group_ids:['200001']} };
const group = { message_type:'group',route_id:'qq-group-200001',target_id:'200001',sender_id:'100002' };
test('public drawing adds only an image grant, not host/QQ management or the owner shelf', () => {
  const runtime = new SoyoRoleRuntime(config), agent={id:'public-draw'}, job={key:'a'.repeat(64),envelope:group};
  runtime.admit(job);runtime.begin(agent,job);
  const visible=runtime.exposed(agent);
  for(const name of ['soyo_draw_image','soyo_image_status','soyo_attach_image','soyo_recall_images'])assert(visible.has(name));
  for(const name of ['bash','soyo_image_shelf','soyo_image_collect','qq_ban','soyo_action_brain'])assert(!visible.has(name),name);
  assert(job.binding.capabilities.includes('images.generate'));
  assert(!job.binding.capabilities.includes('host.root'));
  assert(runtime.executionTools({...job.binding,lane:'action'}).has('soyo_draw_image'));
});
test('deployment toggle, allowlist, scene binding and report boundaries are rechecked', () => {
  assert.equal(imageMayGenerate(config,{envelope:group}),true);
  assert.equal(imageMayGenerate({...config,image_permissions:{enabled:false}},{owner:true}),false);
  assert.equal(imageMayGenerate(config,{envelope:{...group,target_id:'200002',route_id:'qq-group-200002'}}),false);
  assert.equal(imageMayGenerate(config,{envelope:{...group,route_id:'qq-group-200002'}}),false);
  assert.equal(imageMayGenerate(config,{envelope:group,internal:true}),false);
});
test('a known path under the global media root is NOT a public reference grant', async () => {
  const root=await mkdtemp(join(tmpdir(),'image-source-'));
  const scene=join(root,'scene.png'), privateImage=join(root,'owner.png');
  await writeFile(scene,'fixture');await writeFile(privateImage,'private fixture');
  const allowed=new Set([await realpath(scene)]);
  assert.equal((await sceneImagePaths([scene],allowed)).length,1);
  await assert.rejects(sceneImagePaths([privateImage],allowed),/IMAGE_SOURCE/);
  await assert.rejects(sceneImagePaths([scene,null],allowed),/IMAGE_SOURCE/);
});
