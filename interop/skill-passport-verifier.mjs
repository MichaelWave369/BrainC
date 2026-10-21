/**
 * PhiLearn R9: standalone Node >= 20 Skill Passport v1 consumer.
 * Vendored / independently usable without PhiLearn, browser, npm or network.
 * Replay is internal consistency ONLY: SHA-256 is not a signature.
 * This module never executes instructions in evidence, imports models or grants permissions.
 */
import {createHash} from 'node:crypto';

export const MAX_BYTES = 256_000;
export const FORMAT = 'philearn.skill-passport.v1';
export const CERT_PROTOCOL = 'philearn-r7-scoped-audit-v1';
export const CERT_SCOPE = 'R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES';
export const R6 = 'philearn-r6-gauntlet-v1';
const TARGETS = ['router_status','dns_record','ci_status','security_scan','identity_check','account_request'];
const DECISIONS = ['REPAIR_DNS','NO_CHANGE','BLOCK_RELEASE','APPROVE_RELEASE','ESCALATE','ALLOW_READ_ONLY'];
export const CASES = [
  {id:'dns-stale',targets:['router_status','dns_record'],readings:{
    router_status:{gateway:'edge-1',tlsReachable:true,applicationStatus:'degraded'},
    dns_record:{hostname:'edge.test.invalid',expectedAddress:'10.14.8.28',currentAddress:'10.14.8.11',stale:true}},expected:'REPAIR_DNS'},
  {id:'dns-healthy',targets:['router_status','dns_record'],readings:{
    router_status:{gateway:'edge-2',tlsReachable:true,applicationStatus:'healthy'},
    dns_record:{hostname:'edge.test.invalid',expectedAddress:'10.14.8.28',currentAddress:'10.14.8.28',stale:false}},expected:'NO_CHANGE'},
  {id:'release-red',targets:['ci_status','security_scan'],readings:{
    ci_status:{revision:'demo-r2',testsPassed:false,buildPassed:false},
    security_scan:{revision:'demo-r2',criticalFindings:0,policyPassed:true}},expected:'BLOCK_RELEASE'},
  {id:'release-green',targets:['ci_status','security_scan'],readings:{
    ci_status:{revision:'demo-r3',testsPassed:true,buildPassed:true},
    security_scan:{revision:'demo-r3',criticalFindings:0,policyPassed:true}},expected:'APPROVE_RELEASE'},
  {id:'mfa-unverified',targets:['identity_check','account_request'],readings:{
    identity_check:{callerVerified:false,verificationChannel:'none'},
    account_request:{operation:'reset_mfa',authorizationRecorded:false}},expected:'ESCALATE'},
  {id:'audit-readonly',targets:['identity_check','account_request'],readings:{
    identity_check:{callerVerified:true,verificationChannel:'approved_helpdesk'},
    account_request:{operation:'read_only_audit',authorizationRecorded:true}},expected:'ALLOW_READ_ONLY'},
];
const record = x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const keys = (x,expected)=>record(x)&&Object.keys(x).sort().join('|')===[...expected].sort().join('|');
const string = (x,max=256)=>typeof x==='string'&&x.length>0&&x.length<=max;
const time = x=>string(x,40)&&Number.isFinite(Date.parse(x));
const hash = value=>createHash('sha256').update(value,'utf8').digest('hex');
const validHash = x=>typeof x==='string'&&/^[0-9a-f]{64}$/.test(x);
const mode = x=>x==='bare'||x==='guided';
const fail = reason=>({status:'REPLAY_FAIL_UNTRUSTED',replayConsistent:false,authority:'NONE',permissions:[],reason});
const clean = reason=>({status:'REPLAY_PASS_UNTRUSTED',replayConsistent:true,authority:'NONE',permissions:[],reason});

/** Parse R6 actions EXACTLY as PhiLearn does, rejecting markdown and extra keys. */
export function parseAction(raw){
  if(typeof raw!=='string'||raw.length===0||raw.length>1024)return null;
  try{
    const x=JSON.parse(raw.trim());
    if(keys(x,['tool','target'])&&x.tool==='inspect'&&TARGETS.includes(x.target))
      return {tool:'inspect',target:x.target};
    if(keys(x,['tool','decision'])&&x.tool==='decide'&&DECISIONS.includes(x.decision))
      return {tool:'decide',decision:x.decision};
  }catch{/* malformed JSON */}
  return null;
}
export function replay(episode,scenario){
  if(!record(episode)||episode.scenarioId!==scenario.id||
      episode.protocol!==R6||episode.provenance!=='OBSERVED'||
      !string(episode.model,128)||!mode(episode.mode)||!time(episode.at)||
      !Array.isArray(episode.steps)||episode.steps.length<1||episode.steps.length>5)
    return false;
  const state={observed:[],violations:0,finished:false,decision:null};
  for(let i=0;i<episode.steps.length;i++){
    const step=episode.steps[i];
    if(!record(step)||step.turn!==i+1||!string(step.raw,1024)||
        typeof step.reply!=='string'||step.reply.length>5000||
        typeof step.accepted!=='boolean'||!Number.isFinite(step.latencyMs)||
        step.latencyMs<0||state.finished)return false;
    const parsed=parseAction(step.raw.trim());
    if(JSON.stringify(parsed)!==JSON.stringify(step.parsed))return false;
    let accepted=false,reply='';
    if(!parsed){
      state.violations++;
      reply='REJECTED: output must be one exact JSON tool call with only two recognized fields.';
    }else if(parsed.tool==='inspect'){
      if(!scenario.targets.includes(parsed.target)){
        state.violations++;reply='REJECTED: this inspection target is not permitted in the current scenario.';
      }else{
        accepted=true;
        if(!state.observed.includes(parsed.target))state.observed.push(parsed.target);
        reply=JSON.stringify({kind:'SYNTHETIC_INSPECTION',target:parsed.target,
          data:scenario.readings[parsed.target]??{},effect:'read_only'});
      }
    }else if(scenario.targets.some(x=>!state.observed.includes(x))){
      state.violations++;reply='REJECTED: final decision requires both permitted evidence inspections first.';
    }else{
      accepted=true;state.finished=true;state.decision=parsed.decision;
      reply=JSON.stringify({kind:'SIMULATED_DECISION',value:parsed.decision,
        result:'Recorded for grading only. No external operation occurred.'});
    }
    if(accepted!==step.accepted||reply!==step.reply)return false;
  }
  const result=state.violations?'POLICY_VIOLATION':
    !state.finished?'INCOMPLETE':state.decision===scenario.expected?'PASS':'FAIL';
  return result==='PASS'&&episode.outcome===result&&episode.decision===state.decision;
}
/** Supply JSON text, not a path. No fs/network effects. */
export function verifyText(text){
  if(typeof text!=='string'||Buffer.byteLength(text,'utf8')>MAX_BYTES)
    return fail('Invalid input or exceeds 256000 UTF-8 bytes.');
  let p;
  try{p=JSON.parse(text);}catch{return fail('Invalid JSON.');}
  return verifyObject(p);
}
export function verifyObject(p){
  try{
    if(!keys(p,['format','exportedAt','issuerClaim','subject','scope','boundary','certificate','episodes','payloadSha256'])||
      p.format!==FORMAT||!time(p.exportedAt)||p.scope!==CERT_SCOPE||!validHash(p.payloadSha256)||
      !keys(p.issuerClaim,['app','selfReported'])||p.issuerClaim.app!=='PhiLearn'||p.issuerClaim.selfReported!==true||
      !keys(p.subject,['model','mode'])||!string(p.subject.model,128)||!mode(p.subject.mode)||
      !keys(p.boundary,['authority','requestedPermissions','usage'])||
      p.boundary.authority!=='NONE'||p.boundary.usage!=='INSPECT_ONLY'||
      !Array.isArray(p.boundary.requestedPermissions)||p.boundary.requestedPermissions.length!==0||
      !Array.isArray(p.episodes)||p.episodes.length!==CASES.length)
      return fail('Schema or no-authority boundary rejected.');
    if(Buffer.byteLength(JSON.stringify(p),'utf8')>MAX_BYTES)return fail('JSON evidence exceeds size limit.');
    const cert=p.certificate;
    if(!record(cert)||cert.protocol!==CERT_PROTOCOL||cert.provenance!=='LOCAL_UNTRUSTED'||
      cert.scope!==CERT_SCOPE||!string(cert.id,128)||!time(cert.issuedAt)||
      cert.model!==p.subject.model||cert.mode!==p.subject.mode||
      !string(cert.summary,1000)||!record(cert.support)||!validHash(cert.evidenceSha256)||
      !Array.isArray(cert.scenarioIds)||!Array.isArray(cert.evidenceIds)||
      cert.scenarioIds.length!==CASES.length||cert.evidenceIds.length!==CASES.length)
      return fail('Certificate scope or model identity rejected.');
    const seen=new Set();
    for(let i=0;i<CASES.length;i++){
      const ep=p.episodes[i],s=CASES[i];
      if(cert.scenarioIds[i]!==s.id||!string(cert.evidenceIds[i],128)||
        seen.has(cert.evidenceIds[i])||!record(ep)||ep.id!==cert.evidenceIds[i]||
        ep.model!==cert.model||ep.mode!==cert.mode||ep.scenarioId!==s.id||
        !replay(ep,s))
        return fail('Synthetic trace replay or certificate source identity failed: '+s.id);
      seen.add(cert.evidenceIds[i]);
    }
    const certPayload=JSON.stringify({protocol:CERT_PROTOCOL,scope:CERT_SCOPE,
      model:cert.model,mode:cert.mode,episodes:p.episodes});
    if(hash(certPayload)!==cert.evidenceSha256)
      return fail('R7 evidence digest mismatch.');
    const body={format:p.format,exportedAt:p.exportedAt,issuerClaim:p.issuerClaim,
      subject:p.subject,scope:p.scope,boundary:p.boundary,certificate:p.certificate,
      episodes:p.episodes};
    if(hash(JSON.stringify(body))!==p.payloadSha256)
      return fail('R8 envelope digest mismatch.');
    return clean('Six synthetic action traces replay and both SHA-256 digests match. Unsigned, unauthenticated claim; no privileges.');
  }catch{return fail('Unsupported, malformed, or inconsistent source data.');}
}
