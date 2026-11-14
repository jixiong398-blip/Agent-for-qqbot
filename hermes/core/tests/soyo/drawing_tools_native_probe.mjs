// SPDX-License-Identifier: MIT
// Actual pinned defineTool + production handlers; loopback image fixture only.
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtemp,mkdir,writeFile,cp,symlink,realpath,readFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

assert(process.argv[2], 'Pass the installed native runtime and, on Windows, Python executable.');
const native=resolve(process.argv[2]);
const core=fileURLToPath(new URL('../../',import.meta.url));
process.env.SOYO_WORKER_ROOT=core;
if(process.argv[3]) process.env.SOYO_PYTHON=resolve(process.argv[3]);
const root=await mkdtemp(join(tmpdir(),'drawing-scope-'));
await symlink(join(native,'node_modules'),join(root,'node_modules'),process.platform==='win32'?'junction':'dir');
await cp(join(core,'soyo/dsh/host'),join(root,'host'),{recursive:true});
const {registerDrawingTools}=await import(pathToFileURL(join(root,'host/drawing-tools.mjs')));
const media=join(root,'media');await mkdir(media,{mode:0o700});
const image=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==','base64');
const publicImage=join(media,'public.png'),privateImage=join(media,'owner-private.png'),key=join(root,'image-key');
await writeFile(publicImage,image,{mode:0o600});await writeFile(privateImage,image,{mode:0o600});
await writeFile(key,'fixture-only-not-a-provider-key',{mode:0o600});
if(process.platform==='win32'){
 const secured=spawnSync(process.env.SOYO_PYTHON||'python',['-B','-c',
  'import sys;sys.path.insert(0,sys.argv[1]);from soyo.platform import protect;protect(sys.argv[2],directory=True);protect(sys.argv[3])',core,root,key],{encoding:'utf8'});
 assert.equal(secured.status,0,secured.stderr);
}
let calls=0,receivedReference=false;
const server=http.createServer(async(req,res)=>{
  const chunks=[];for await(const part of req)chunks.push(part);
  const body=Buffer.concat(chunks);calls++;
  assert.equal(req.url,'/v1/images/edits');
  receivedReference=body.includes(image);
  res.writeHead(200,{'Content-Type':'application/json'});
  res.end(JSON.stringify({data:[{b64_json:image.toString('base64')}]}));
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const config={media_root:media,image_permissions:{enabled:true,allow_group_members:true,group_ids:['200001']},
 image_gen:{enabled:true,base_url:'http://127.0.0.1:'+server.address().port+'/v1',model:'fixture-image',key_file:key,timeout_ms:5000}};
let trace={envelope:{route_id:'qq-group-200001',target_id:'200001',message_type:'group'},image_paths:new Set([await realpath(publicImage)])};
const tools=new Map();
registerDrawingTools({tools:{register:tool=>tools.set(tool.name,tool)}},{config,current:()=>trace,owner:()=>false,roots:()=>[],logger:{}});
try{
 const exec={signal:new AbortController().signal};
 const status=await tools.get('soyo_image_status').execute({},exec);
 assert(status.configured&&status.allowed);
 for(const field of ['base_url','key_file','key_file_present'])assert(!(field in status));
 await assert.rejects(tools.get('soyo_draw_image').execute({prompt:'fixture',reference_images:[privateImage]},exec),/IMAGE_SOURCE/);
 assert.equal(calls,0,'a known private path must never reach even the fixture provider');
 const generated=await tools.get('soyo_draw_image').execute({prompt:'fixture',reference_images:[publicImage]},exec);
 assert.equal(generated.state,'created');assert.equal(generated.reference_images_used,1);
 assert(generated.path.startsWith(join(media,'scene-generated')));
 assert.deepEqual(await readFile(generated.path),image);assert(receivedReference);
 assert(trace.image_paths.has(await realpath(generated.path)));
 assert(!tools.has('soyo_attach_image'),'an image executor is not another QQ writer');
 config.image_permissions.allow_group_members=false;
 await assert.rejects(tools.get('soyo_draw_image').execute({prompt:'fixture'},exec),/IMAGE_PERMISSION/);
 assert.equal(calls,1);
 console.log(JSON.stringify({private_reference_denied_before_request:true,scene_reference_uploaded:true,
  verified_image_staged:true,permission_rechecked:true,public_status_redacted:true,real_image_provider_requests:0,fixture_requests:calls}));
}finally{await new Promise(r=>server.close(r));}
