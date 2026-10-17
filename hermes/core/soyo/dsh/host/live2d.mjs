// SPDX-License-Identifier: MIT
// Explicit owner-granted desktop effects; never QQ publication or free HTTP.
import http from 'node:http';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { openPrivate, endpointOptions } from './platform.mjs';

export function registerLive2d(scope, config, authorize) {
  if (!config.live2d_enabled) return [];
  scope.tools.register(defineTool({name:'soyo_live2d',
    description:'操作当前实例可选 Live2D：列模型、切模型、表情、动作、视线或尺寸。只接受本机已授权桌面，不发送 QQ；accepted 不是动画已完成。',
    parameters:{action:{type:'string',enum:['models','switch_model','expression','motion','look','size'],required:true},
      character:{type:'string'},costume:{type:'string'},name:{type:'string'},group:{type:'string'},
      index:{type:'number'},x:{type:'number'},y:{type:'number'},percent:{type:'number'}},
    output:{schema:{type:'object',additionalProperties:true},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},
    async execute(args, exec) {
      authorize(exec);
      const key = await openPrivate(config.live2d_key_file, 129);
      let secret; try { secret = (await key.readFile('utf8')).trim(); } finally { await key.close(); }
      const command = {type:args.action, ...Object.fromEntries(Object.entries(args).filter(([name])=>name!=='action'))};
      if (JSON.stringify(command).length > 2000 || Object.values(command).some(value=>typeof value==='number'&&!Number.isFinite(value))) throw Error('Bounded desktop action required');
      const raw = args.action === 'models' ? undefined : JSON.stringify(command);
      return new Promise((resolve,reject)=>{
        const request = http.request({...endpointOptions(config,'live2d',raw?'/cmd':'/api/models'),
          method:raw?'POST':'GET',signal:exec.signal,headers:{Authorization:'Bearer '+secret,
            ...(raw?{'Content-Type':'application/json','Content-Length':Buffer.byteLength(raw)}:{})}},response=>{
          const parts=[];let size=0;
          response.on('data',part=>{size+=part.length;if(size>256*1024)request.destroy(Error('Desktop response too large'));else parts.push(part);});
          response.on('error',()=>reject(Error('Desktop response interrupted; do not blindly repeat effects')));
          response.on('end',()=>{
            if(response.statusCode!==200)return reject(Error('Desktop action rejected'));
            try{resolve({state:raw?'accepted':'observed',result:JSON.parse(Buffer.concat(parts).toString('utf8')),qq_sends:0});}
            catch{reject(Error('Desktop response invalid; effect not confirmed'));}
          });
        });
        request.setTimeout(8000,()=>request.destroy(Error('Desktop request timed out; effect unconfirmed')));
        request.on('error',()=>reject(Error('Configured desktop unavailable; effect unconfirmed')));request.end(raw);
      });
    }}));
  return ['soyo_live2d'];
}
