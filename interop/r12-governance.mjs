/**
 * PhiLearn R12: tamper-evident OFFLINE operator governance event ledger.
 * Ed25519 signatures by separately pinned operator keys, chained event hashes.
 * THIS DOES NOT AUTHORIZE ANY OPERATION, GRANT ANY ACCESS, OR AUTO-ENROLL AGENTS.
 *
 * A hash chain is NOT immutable storage. A receiver needs a checkpoint pinned
 * outside the editable ledger; a malicious operator can still sign fabricated
 * events. Timestamps and operator IDs are asserted, not independently attested.
 */
import {createHash,createPrivateKey,createPublicKey,sign,verify} from 'node:crypto';
import {verifySignedObject} from './r10-signed-passport.mjs';
import {signedEnvelopeDigest} from './r11-enrollment.mjs';

export const LEDGER_FORMAT='philearn.r12.governance-ledger.v1';
export const EVENT_FORMAT='philearn.r12.operator-event.v1';
export const TRUST_FORMAT='philearn.r12.operator-trust.v1';
export const CHECKPOINT_FORMAT='philearn.r12.checkpoint.v1';
export const DOMAIN='PHILEARN-R12-OPERATOR-EVENT-V1';
export const SCOPE='R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES';
export const MAX_LEDGER_BYTES=192_000;
export const GENESIS='0'.repeat(64);
const MAX_EVENTS=128, MAX_HOURS=168, MAX_MS=MAX_HOURS*3_600_000;
const obj=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const exact=(x,k)=>obj(x)&&Object.keys(x).sort().join('|')===[...k].sort().join('|');
const label=x=>typeof x==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/.test(x);
const model=x=>typeof x==='string'&&x.length>0&&x.length<=128;
const hex=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const keyId=x=>typeof x==='string'&&/^sha256:[a-f0-9]{64}$/.test(x);
const iso=x=>typeof x==='string'&&x.length<=40&&/^\d{4}-\d\d-\d\dT/.test(x)&&Number.isFinite(Date.parse(x));
const b64=x=>typeof x==='string'&&x.length<1200&&/^[A-Za-z0-9+/]+={0,2}$/.test(x)&&Buffer.from(x,'base64').toString('base64')===x;
const hash=x=>createHash('sha256').update(JSON.stringify(x),'utf8').digest('hex');
const publicKey=x=>x?.type==='public'?x:createPublicKey(x);
const privateKey=x=>x?.type==='private'?x:createPrivateKey(x);
const fingerprint=x=>{
  const key=publicKey(x);
  if(key.asymmetricKeyType!=='ed25519')throw Error('Only Ed25519 operator keys allowed.');
  return 'sha256:'+createHash('sha256').update(key.export({format:'der',type:'spki'})).digest('hex');
};
const verifiedMessage=event=>Buffer.from(DOMAIN+'\n'+JSON.stringify(event)+'\n','utf8');
const fail=(status,reason,headHash=GENESIS,eventCount=0)=>({
  status,reason,chainValid:false,headHash,eventCount,reviewApproved:false,
  authority:'NONE',permissions:[],actionAllowed:false,
});
const zero=(status,reason,headHash,count,approved=false)=>({
  status,reason,chainValid:true,headHash,eventCount:count,reviewApproved:approved,
  authority:'NONE',permissions:[],actionAllowed:false,
});
export const emptyLedger=()=>({format:LEDGER_FORMAT,entries:[]});
export const emptyCheckpoint=()=>({format:CHECKPOINT_FORMAT,count:0,headHash:GENESIS});
export function createOperatorRecord(operatorId,operatorPublicKey){
  if(!label(operatorId))throw Error('Operator ID must be a bounded ASCII label.');
  const key=publicKey(operatorPublicKey);
  const keyId=fingerprint(key);
  return {operatorId,keyId,publicKeySpkiBase64:key.export({format:'der',type:'spki'}).toString('base64'),active:true};
}
export function validateOperatorTrust(store){
  if(!exact(store,['format','operators'])||store.format!==TRUST_FORMAT||
    !Array.isArray(store.operators)||store.operators.length>40||
    Buffer.byteLength(JSON.stringify(store),'utf8')>16_000)return false;
  const seen=new Set();
  for(const op of store.operators){
    if(!exact(op,['operatorId','keyId','publicKeySpkiBase64','active'])||
      !label(op.operatorId)||!keyId(op.keyId)||!b64(op.publicKeySpkiBase64)||
      typeof op.active!=='boolean')return false;
    let key;
    try{
      key=createPublicKey({key:Buffer.from(op.publicKeySpkiBase64,'base64'),format:'der',type:'spki'});
      if(fingerprint(key)!==op.keyId)return false;
    }catch{return false;}
    const id=op.operatorId+'\u0000'+op.keyId;
    if(seen.has(id))return false;
    seen.add(id);
  }
  return true;
}
function operatorByPrivate(store,id,privatePem){
  const key=privateKey(privatePem);
  if(key.asymmetricKeyType!=='ed25519')throw Error('Ed25519 private signing key required.');
  const opKeyId=fingerprint(createPublicKey(key));
  if(!validateOperatorTrust(store)||store.operators.filter(o=>o.active&&
    o.operatorId===id&&o.keyId===opKeyId).length!==1)
    throw Error('Private key not operator-pinned and active in external trust store.');
  return {key,opKeyId};
}
export function verifyLedger(ledger,operatorStore){
  if(!validateOperatorTrust(operatorStore))return fail('OPERATOR_TRUST_INVALID','Operator public key pins absent or malformed.');
  if(!exact(ledger,['format','entries'])||ledger.format!==LEDGER_FORMAT||
    !Array.isArray(ledger.entries)||ledger.entries.length>MAX_EVENTS||
    Buffer.byteLength(JSON.stringify(ledger),'utf8')>MAX_LEDGER_BYTES)
    return fail('LEDGER_INVALID','Malformed or excessive event ledger.');
  const state=new Map();let prevHash=GENESIS,prevAt=-Infinity;
  for(let i=0;i<ledger.entries.length;i++){
    const entry=ledger.entries[i];
    if(!exact(entry,['event','signature'])||!b64(entry.signature)||
      Buffer.from(entry.signature,'base64').length!==64)
      return fail('ENTRY_INVALID','Malformed event signature at position '+(i+1),prevHash,i);
    const e=entry.event;
    if(!exact(e,['format','seq','prevHash','type','enrollmentId','envelopeSha256','issuerId',
      'issuerKeyId','model','scope','operatorId','operatorKeyId','at','expiresAt'])||
      e.format!==EVENT_FORMAT||e.seq!==i+1||e.prevHash!==prevHash||
      !['APPROVE_INSPECTION','REVOKE_INSPECTION','EXPIRE_INSPECTION'].includes(e.type)||
      !hex(e.enrollmentId)||!hex(e.envelopeSha256)||!label(e.issuerId)||
      !keyId(e.issuerKeyId)||!model(e.model)||e.scope!==SCOPE||
      !label(e.operatorId)||!keyId(e.operatorKeyId)||!iso(e.at)||
      (e.expiresAt!==null&&!iso(e.expiresAt)))
      return fail('ENTRY_INVALID','Malformed, out-of-order or unlinked event at '+(i+1),prevHash,i);
    const at=Date.parse(e.at);
    if(at<prevAt)return fail('CLOCK_REGRESSION','Event timestamps regressed.',prevHash,i);
    prevAt=at;
    const pinned=operatorStore.operators.filter(o=>o.active&&
      o.operatorId===e.operatorId&&o.keyId===e.operatorKeyId);
    if(pinned.length!==1)return fail('OPERATOR_NOT_PINNED','Event signed by unknown/inactive operator.',prevHash,i);
    let valid=false;
    try{
      valid=verify(null,verifiedMessage(e),createPublicKey({
        key:Buffer.from(pinned[0].publicKeySpkiBase64,'base64'),format:'der',type:'spki',
      }),Buffer.from(entry.signature,'base64'));
    }catch{/* malformed signature */}
    if(!valid)return fail('SIGNATURE_INVALID','Operator event signature failed at '+(i+1),prevHash,i);
    const prior=state.get(e.enrollmentId);
    if(e.type==='APPROVE_INSPECTION'){
      if(prior||e.expiresAt===null||
        Date.parse(e.expiresAt)<=at||Date.parse(e.expiresAt)-at>MAX_MS)
        return fail('EVENT_TRANSITION_INVALID','Duplicate enrollment or invalid approval lease.',prevHash,i);
      state.set(e.enrollmentId,{event:e,closed:false});
    }else{
      if(!prior||prior.closed||e.expiresAt!==null||
        prior.event.envelopeSha256!==e.envelopeSha256||
        prior.event.issuerId!==e.issuerId||
        prior.event.issuerKeyId!==e.issuerKeyId||
        prior.event.model!==e.model||prior.event.scope!==e.scope)
        return fail('EVENT_TRANSITION_INVALID','Closure without matching active approval.',prevHash,i);
      if(e.type==='EXPIRE_INSPECTION'&&at<Date.parse(prior.event.expiresAt))
        return fail('PREMATURE_EXPIRY','Explicit expiry predates stated lease end.',prevHash,i);
      prior.closed=true;prior.closedType=e.type;
    }
    prevHash=hash(entry);
  }
  return {...zero('CHAIN_VALID_UNANCHORED',
    'Operator signatures, event order and chain verified. An external checkpoint is still required to detect truncation.',prevHash,ledger.entries.length),
    latestStates:state};
}
export function createCheckpoint(ledger,operatorStore){
  const result=verifyLedger(ledger,operatorStore);
  if(!result.chainValid)throw Error('Cannot checkpoint invalid governance ledger: '+result.reason);
  return {format:CHECKPOINT_FORMAT,count:result.eventCount,headHash:result.headHash};
}
export function checkpointMatches(checkpoint,verification){
  return exact(checkpoint,['format','count','headHash'])&&
    checkpoint.format===CHECKPOINT_FORMAT&&
    Number.isSafeInteger(checkpoint.count)&&checkpoint.count>=0&&
    hex(checkpoint.headHash)&&verification.chainValid&&
    checkpoint.count===verification.eventCount&&checkpoint.headHash===verification.headHash;
}
function newEntry(type,base,at,expiresAt,operatorId,operatorKeyId,ledger,signingKey,verification){
  const event={format:EVENT_FORMAT,seq:ledger.entries.length+1,
    prevHash:verification.headHash,type,enrollmentId:base.enrollmentId,
    envelopeSha256:base.envelopeSha256,issuerId:base.issuerId,
    issuerKeyId:base.issuerKeyId,model:base.model,scope:SCOPE,
    operatorId,operatorKeyId,at,expiresAt};
  const signature=sign(null,verifiedMessage(event),signingKey).toString('base64');
  return {event,signature};
}
export function appendApproval(signed,passportTrust,operatorStore,ledger,operatorPrivateKey,operatorId,
  at=new Date().toISOString(),leaseHours=24,confirmed=false,knownCheckpoint=null){
  if(confirmed!==true)throw Error('Explicit human operator confirmation required.');
  if(!iso(at)||!Number.isInteger(leaseHours)||leaseHours<1||leaseHours>MAX_HOURS)
    throw Error('Invalid review timestamp or lease (1–168 hours).');
  const check=verifyLedger(ledger,operatorStore);
  if(!check.chainValid)throw Error(check.reason);
  if(knownCheckpoint&&!checkpointMatches(knownCheckpoint,check))
    throw Error('Operator checkpoint does not match current ledger head.');
  if(ledger.entries.length>0&&!knownCheckpoint)
    throw Error('Existing ledger requires an independently retained checkpoint before appending.');
  if(!iso(signed?.signedAt)||Date.parse(at)<Date.parse(signed.signedAt))
    throw Error('Operator review cannot be dated before claimed passport signing.');
  const source=verifySignedObject(signed,passportTrust);
  if(!source.signatureValid||!source.keyPinned||!source.sourceReplayConsistent)
    throw Error('Cannot approve without R10 independently pinned signed R6 evidence.');
  const {key,opKeyId}=operatorByPrivate(operatorStore,operatorId,operatorPrivateKey);
  const envelopeSha256=signedEnvelopeDigest(signed);
  const enrollmentId=hash({issuerId:signed.issuerId,keyId:signed.keyId,
    envelopeSha256,scope:signed.passport.scope});
  const base={enrollmentId,envelopeSha256,issuerId:signed.issuerId,issuerKeyId:signed.keyId,
    model:signed.passport.subject.model};
  const entry=newEntry('APPROVE_INSPECTION',base,at,
    new Date(Date.parse(at)+leaseHours*3600_000).toISOString(),
    operatorId,opKeyId,ledger,key,check);
  const updated={format:LEDGER_FORMAT,entries:[...ledger.entries,entry]};
  if(!verifyLedger(updated,operatorStore).chainValid)
    throw Error('Generated approval failed deterministic ledger validation.');
  return updated;
}
export function appendClosure(type,enrollmentId,operatorStore,ledger,operatorPrivateKey,operatorId,
  at=new Date().toISOString(),confirmed=false,knownCheckpoint=null){
  if(confirmed!==true)throw Error('Explicit human operator confirmation required.');
  if(!['REVOKE_INSPECTION','EXPIRE_INSPECTION'].includes(type)||!hex(enrollmentId)||!iso(at))
    throw Error('Invalid closure type, enrollment ID or timestamp.');
  const check=verifyLedger(ledger,operatorStore);
  if(!check.chainValid)throw Error(check.reason);
  if(!knownCheckpoint||!checkpointMatches(knownCheckpoint,check))
    throw Error('Closure requires matching independently retained prior checkpoint.');
  const current=check.latestStates.get(enrollmentId);
  if(!current||current.closed)throw Error('Enrollment is absent or already closed.');
  const {key,opKeyId}=operatorByPrivate(operatorStore,operatorId,operatorPrivateKey);
  const e=current.event;
  const base={enrollmentId,envelopeSha256:e.envelopeSha256,issuerId:e.issuerId,
    issuerKeyId:e.issuerKeyId,model:e.model};
  const entry=newEntry(type,base,at,null,operatorId,opKeyId,ledger,key,check);
  const updated={format:LEDGER_FORMAT,entries:[...ledger.entries,entry]};
  if(!verifyLedger(updated,operatorStore).chainValid)
    throw Error('Generated closure failed deterministic ledger validation.');
  return updated;
}
/**
 * All outputs permanently deny tool operations. Pinned checkpoint must be
 * maintained through an independent channel; the supplied clock is local.
 */
export function evaluateGovernance(signed,passportTrust,operatorStore,ledger,checkpoint,
  now=new Date().toISOString()){
  if(!iso(now))return fail('INVALID_CLOCK','Bounded local clock required.');
  const chain=verifyLedger(ledger,operatorStore);
  if(!chain.chainValid)return chain;
  if(!checkpointMatches(checkpoint,chain))
    return zero('UNANCHORED_OR_CHANGED','Missing/outdated independent head checkpoint; no inspection enrollment.',chain.headHash,chain.eventCount);
  const source=verifySignedObject(signed,passportTrust);
  if(!source.signatureValid||!source.sourceReplayConsistent||!source.keyPinned)
    return zero('SOURCE_REJECTED','Pinned R10 signature or synthetic source replay rejected.',chain.headHash,chain.eventCount);
  const envelopeSha256=signedEnvelopeDigest(signed);
  const enrollmentId=hash({issuerId:signed.issuerId,keyId:signed.keyId,
    envelopeSha256,scope:signed.passport.scope});
  const state=chain.latestStates.get(enrollmentId);
  if(!state)return zero('NOT_ENROLLED','Signed evidence has no operator-signed approval event.',chain.headHash,chain.eventCount);
  const e=state.event;
  if(e.envelopeSha256!==envelopeSha256||e.issuerId!==signed.issuerId||
    e.issuerKeyId!==signed.keyId||e.model!==signed.passport.subject.model||
    e.scope!==signed.passport.scope)
    return zero('SOURCE_MISMATCH','Approval bound to different evidence.',chain.headHash,chain.eventCount);
  if(state.closed)return zero(state.closedType==='REVOKE_INSPECTION'?'REVOKED':'EXPIRED_EVENT',
    'Operator-signed closure is terminal for this enrollment.',chain.headHash,chain.eventCount);
  const clock=Date.parse(now);
  if(clock<Date.parse(e.at))return zero('NOT_YET_VALID','Operator-claimed review time in future.',chain.headHash,chain.eventCount);
  if(clock>=Date.parse(e.expiresAt))return zero('EXPIRED','Inspection lease expired.',chain.headHash,chain.eventCount);
  return zero('INSPECTION_APPROVED_WITH_SIGNED_HISTORY',
    'Pinned operator-signed evidence review confirmed against independently held checkpoint. No action authorization.',chain.headHash,chain.eventCount,true);
}
