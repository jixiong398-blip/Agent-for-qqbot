'use strict';
let csrf = '', config = null, refreshBusy = false, personaDigest = '';
const $ = id => document.getElementById(id);
const modelId = (lane, key) => 'model_' + lane + '_' + key;
const notice = text => { $('notice').textContent = text; };
async function api(path, body) {
  const response = await fetch(path, {credentials:'same-origin', cache:'no-store', headers:body === undefined ? {} : {'Content-Type':'application/json','X-Agent-CSRF':csrf}, ...(body === undefined ? {} : {method:'POST',body:JSON.stringify(body)})});
  const value = await response.json();
  if (!response.ok) {const error=new Error(value.error || `HTTP ${response.status}`);error.status=response.status;throw error;}
  return value;
}
function input(parent, id, title, type='text', options) {
  const label = document.createElement('label'); label.append(document.createTextNode(title));
  const node = document.createElement(options ? 'select' : 'input'); node.id = id;
  if (options) for (const [value,text] of options) { const item = document.createElement('option'); item.value=value; item.textContent=text; node.append(item); }
  else { node.type=type; if(type==='password') node.autocomplete='new-password'; }
  label.append(node); parent.append(label); return node;
}
for (const lane of ['character','action']) {
  const field = document.createElement('fieldset'), legend = document.createElement('legend'); legend.textContent=lane==='character'?'主角色模型':'行动 / 审阅模型'; field.append(legend); $('model-fields').append(field);
  field.id=lane+'-fields';
  for (const [key,title,type] of [['name','模型 ID','text'],['base_url','API Base URL','url'],['api_key','API Key（留空保留）','password'],['context_window','已确认的上下文上限','number'],['max_tokens','输出预算','number'],['reasoning_effort','思考强度（留空为供应端默认）','text']]) input(field, modelId(lane,key),title,type);
  input(field,modelId(lane,'api'),'协议','text',[['openai-completions','Chat Completions'],['openai-responses','Responses']]);
  input(field,modelId(lane,'auth_mode'),'认证方式','text',[['bearer','API Key'],['none','本地免 Key（仅限回环地址）']]);
  input(field,modelId(lane,'vision'),'已明确支持图片输入','text',[['no','否'],['yes','是']]);
  input(field,modelId(lane,'reasoning_efforts'),'思考档位映射（可选 JSON，按供应商文档）');
  const list=document.createElement('datalist');list.id=lane+'-model-list';field.append(list);$(modelId(lane,'name')).setAttribute('list',list.id);
  const probe=document.createElement('button');probe.type='button';probe.className='secondary';probe.textContent='从已保存的供应商读取模型列表（不推理）';
  probe.addEventListener('click',async()=>{probe.disabled=true;try{const value=await api('/api/models/list',{lane});list.replaceChildren();for(const name of value.models){const option=document.createElement('option');option.value=name;list.append(option);}notice('已读取 '+value.models.length+' 个模型；可在模型 ID 输入框选择，也可手动输入。');}catch(error){notice(error.message);}finally{probe.disabled=false;}});field.append(probe);
}
const ports=['management_port','native_port','native_upstream_port','channel_port','automation_port','agent_line_port','live2d_port'];
for (const key of ports) input($('port-fields'),key,key,'number');
function showConfig(value) {
  config=value;
  for (const key of ['character_name','host_permission_mode','time_zone',...ports]) $(key).value=value[key]??'';
  for(const lane of ['character','action']) {
    const route=value.models[lane]||{};
    for(const key of ['name','base_url','api','context_window','max_tokens','reasoning_effort','auth_mode']) $(modelId(lane,key)).value=route[key]??(key==='api'?'openai-completions':key==='auth_mode'?'bearer':'');
    $(modelId(lane,'api_key')).value=''; $(modelId(lane,'api_key')).placeholder=route.api_key_configured?'已配置，留空保留':''; $(modelId(lane,'vision')).value=route.vision?'yes':'no';
    $(modelId(lane,'reasoning_efforts')).value=route.reasoning_efforts?JSON.stringify(route.reasoning_efforts):'';
  }
  for(const key of ['account_id','http_url','ws_url','config_directory']) $(key).value=value.onebot[key]||'';
  $('admin_ids').value=(value.onebot.admin_ids||[]).join(','); $('onebot_token').value='';
  $('onebot_token').placeholder=value.onebot.token_configured?'已配置，留空保留':'';
  $('napcat_directory').value=value.napcat.directory||''; $('knowledge_directory').value=value.knowledge.directory||''; $('live2d_directory').value=value.live2d.directory||'';
  $('live2d_enabled').value=value.live2d.enabled?'yes':'no';
  $('qq_enabled').value=value.onebot.enabled?'yes':'no';
  $('action_uses_character').value=value.action_uses_character?'yes':'no';
  $('start-native').textContent=value.onebot.enabled?'一键启动原生 Web + QQ':'一键启动原生 Web';
  fillOptions('model-profiles',Object.keys(value.model_profiles||{}));
  updateModelFields();
  const link=$('native-link'); link.href=`http://${value.native_host}:${value.native_port}/`; link.hidden=false;
}
function fillOptions(id,values) {const select=$(id),old=select.value;select.replaceChildren();for(const value of values){const option=document.createElement('option');option.value=value;option.textContent=value;select.append(option);}if(values.includes(old))select.value=old;}
function updateModelFields() {
  const same=$('action_uses_character').value==='yes';$('action-fields').hidden=same;
  for(const node of $('action-fields').querySelectorAll('input,select,button'))node.disabled=same;
  for(const lane of ['character','action']) {
    const secret=$(modelId(lane,'api_key')),none=$(modelId(lane,'auth_mode')).value==='none';secret.disabled=none||(lane==='action'&&same);
    secret.placeholder=none?'本地免 Key；不会使用其他供应商凭据':config?.models[lane]?.api_key_configured?'已配置，留空保留':'';
  }
}
for(const id of ['action_uses_character',modelId('character','auth_mode'),modelId('action','auth_mode')])$(id).addEventListener('change',updateModelFields);
function showPersona(value) {$('soul').value=value.text;personaDigest=value.digest;fillOptions('persona-presets',value.presets);}
async function loadPersona() {showPersona(await api('/api/persona'));}
async function refresh() {
  if(refreshBusy||!csrf) return; refreshBusy=true;
  try {
    const status=await api('/api/status'); $('services').replaceChildren();
    for(const [name,value] of Object.entries(status.services)) {
      const row=document.createElement('div'); row.className='service';
      const text=document.createElement('span'); text.textContent=`${name} · ${value.state}${value.pid?' · PID '+value.pid:''}`; if(value.running) text.className='running'; row.append(text);
      if(['napcat','live2d'].includes(name)) {const button=document.createElement('button'); button.type='button';button.className='secondary';button.dataset.operation=value.running?'stop':'start';button.dataset.service=name;button.textContent=value.running?'停止本实例进程':'启动';row.append(button);}
      $('services').append(row);
    }
    const logs=await api('/api/logs?service='+encodeURIComponent($('log-service').value)); const box=$('logs');const bottom=box.scrollHeight-box.scrollTop-box.clientHeight<50;box.textContent=logs.lines.join('\n');if(bottom)box.scrollTop=box.scrollHeight;
  } catch(error) {notice(error.message);} finally {refreshBusy=false;}
}
async function enter() {csrf=(await api('/api/csrf')).csrf;showConfig(await api('/api/config'));await loadPersona();$('login').hidden=true;$('workspace').hidden=false;await refresh();}
$('login-form').addEventListener('submit',async event=>{event.preventDefault();try{await api('/api/login',{key:$('login-key').value});$('login-key').value='';await enter();notice('已登录当前实例');}catch(error){notice(error.message);}});
$('config-form').addEventListener('submit',async event=>{event.preventDefault();if(!config)return;try{
  const models={};for(const lane of ['character','action']) {if(lane==='action'&&$('action_uses_character').value==='yes')continue;models[lane]={};for(const key of ['name','base_url','api_key','api','reasoning_effort','auth_mode'])models[lane][key]=$(modelId(lane,key)).value.trim();for(const key of ['context_window','max_tokens'])models[lane][key]=Number($(modelId(lane,key)).value);models[lane].vision=$(modelId(lane,'vision')).value==='yes';}
  const changes={character_name:$('character_name').value.trim(),models,host_permission_mode:$('host_permission_mode').value,time_zone:$('time_zone').value.trim(),onebot:{account_id:$('account_id').value.trim(),admin_ids:$('admin_ids').value.split(',').map(x=>x.trim()).filter(Boolean),http_url:$('http_url').value.trim(),ws_url:$('ws_url').value.trim(),token:$('onebot_token').value,config_directory:$('config_directory').value.trim()},napcat:{directory:$('napcat_directory').value.trim()},knowledge:{directory:$('knowledge_directory').value.trim()},live2d:{directory:$('live2d_directory').value.trim()}};
  for(const lane of Object.keys(models))models[lane].reasoning_efforts=JSON.parse($(modelId(lane,'reasoning_efforts')).value.trim()||'{}');
  for(const key of ports)changes[key]=Number($(key).value);
  changes.onebot.enabled=$('qq_enabled').value==='yes';changes.action_uses_character=$('action_uses_character').value==='yes';
  changes.live2d.enabled=$('live2d_enabled').value==='yes';
  showConfig(await api('/api/config',{revision:config.revision,changes}));notice('配置已保存，密钥不回显。端口变更需重启控制台。');
}catch(error){notice(error.message);}});
$('persona-form').addEventListener('submit',async event=>{event.preventDefault();try{showPersona(await api('/api/persona',{text:$('soul').value,digest:personaDigest}));notice('人格已保存；旧文件已备份');}catch(error){notice(error.message);}});
$('persona-import').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;if(file.size>256*1024){notice('人格文件不能超过 256 KiB');return;}$('soul').value=await file.text();notice('已导入编辑区，点击保存才会应用');});
$('persona-reload').addEventListener('click',()=>loadPersona().catch(error=>notice(error.message)));
for(const operation of ['save_preset','use_preset'])$(operation==='save_preset'?'persona-preset-save':'persona-preset-use').addEventListener('click',async()=>{try{const name=$(operation==='save_preset'?'persona-preset-name':'persona-presets').value;showPersona(await api('/api/persona',{operation,name,text:$('soul').value,digest:personaDigest}));notice(operation==='save_preset'?'人格预设已保存；尚未更改当前人格':'人格预设已应用，旧人格已备份；角色名可在实例配置单独修改');}catch(error){notice(error.message);}});
for(const operation of ['save','use','delete'])$('model-profile-'+operation).addEventListener('click',async()=>{try{const name=$(operation==='save'?'model-profile-name':'model-profiles').value;showConfig(await api('/api/model-profiles',{operation,name,revision:config.revision}));notice(operation==='use'?'供应商方案已应用；启动后生效':'供应商方案已更新');}catch(error){notice(error.message);}});
document.addEventListener('click',async event=>{const button=event.target.closest('[data-operation]');if(!button)return;button.disabled=true;try{notice('正在处理，请勿重复点击…');await api('/api/services/'+button.dataset.operation,{service:button.dataset.service});notice('操作已完成，请核对日志与实际连接状态');await refresh();}catch(error){notice(error.message);}finally{button.disabled=false;}});
$('accounts-refresh').addEventListener('click',async()=>{try{const result=await api('/api/napcat/accounts');$('accounts').replaceChildren();for(const row of result.accounts){const option=document.createElement('option');option.value=row.account_id;option.textContent=row.account_id;$('accounts').append(option);}notice(result.accounts.length?'账号列表已读取（不包含 token）':'未找到账号；先扫码登录并保存配置目录');}catch(error){notice(error.message);}});
$('account-select').addEventListener('click',async()=>{try{showConfig(await api('/api/napcat/accounts/select',{account_id:$('accounts').value}));notice('账号已选择；凭据仅保存在当前实例');}catch(error){notice(error.message);}});
enter().catch(error=>{if(error.status===401)$('login').hidden=false;else notice('无法连接实例：'+error.message);});setInterval(refresh,2500);
