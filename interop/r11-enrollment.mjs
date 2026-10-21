/**
 * PhiLearn R11: offline, explicit, INSPECTION-ONLY enrollment.
 *
 * Three independent gates:
 *  (1) R10 signed by a recipient-pinned public key, with replayable R6 evidence;
 *  (2) receiver-local manual review of the exact signed envelope, with expiry;
 *  (3) separate runtime authorization which this module NEVER provides.
 *
 * Registry is operator-controlled local JSON, NOT authenticated or signed.
 * Never use its approval record as a credential or tool policy decision.
 */
import {createHash} from 'node:crypto';
import {verifySignedObject} from './r10-signed-passport.mjs';

export const ENROLLMENT_FORMAT='philearn.r11.inspection-enrollment.v1';
export const ENROLLMENT_MAX_BYTES=48_000;
const MAX_ENTRIES=64;
const MAX_LEASE_MS=7*24*60*60*1000;
const hash=x=>createHash('sha256').update(JSON.stringify(x),'utf8').digest('hex');
const record=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const exact=(x,fields)=>record(x)&&Object.keys(x).sort().join('|')===[...fields].sort().join('|');
const label=x=>typeof x==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/.test(x);
const iso=x=>typeof x==='string'&&x.length<=40&&/^\d{4}-\d\d-\d\dT/.test(x)&&Number.isFinite(Date.parse(x));
const digest=x=>typeof x==='string'&&/^[0-9a-f]{64}$/.test(x);
const inspectOnly=()=>({authority:'NONE',permissions:[],actionAllowed:false});
const verdict=(status,reason,sig=false,approved=false)=>({
  status,reason,signatureValid:sig,reviewApproved:approved,
  inspectionOnly:approved,...inspectOnly(),
});
export const emptyRegistry=()=>({format:ENROLLMENT_FORMAT,entries:[]});
export function signedEnvelopeDigest(signed){
  return hash(signed);
}
export function validateEnrollmentRegistry(registry){
  if(!exact(registry,['format','entries'])||registry.format!==ENROLLMENT_FORMAT||
    !Array.isArray(registry.entries)||registry.entries.length>MAX_ENTRIES||
    Buffer.byteLength(JSON.stringify(registry),'utf8')>ENROLLMENT_MAX_BYTES)return false;
  const seen=new Set();
  for(const entry of registry.entries){
    if(!exact(entry,['enrollmentId','envelopeSha256','issuerId','keyId',
      'model','scope','operatorId','reviewedAt','expiresAt','state'])||
      !digest(entry.enrollmentId)||!digest(entry.envelopeSha256)||
      !label(entry.issuerId)||!/^sha256:[a-f0-9]{64}$/.test(entry.keyId)||
      typeof entry.model!=='string'||entry.model.length<1||entry.model.length>128||
      entry.scope!=='R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES'||
      !label(entry.operatorId)||!iso(entry.reviewedAt)||!iso(entry.expiresAt)||
      !['APPROVED_INSPECTION','REVOKED'].includes(entry.state))return false;
    const reviewed=Date.parse(entry.reviewedAt),until=Date.parse(entry.expiresAt);
    if(until<=reviewed||until-reviewed>MAX_LEASE_MS||seen.has(entry.enrollmentId))return false;
    seen.add(entry.enrollmentId);
  }
  return true;
}
/** Records explicit review only; never a policy authorization. */
export function approveForInspection(signed,trustStore,registry,operatorId,
  reviewedAt=new Date().toISOString(),leaseHours=24,operatorConfirmed=false){
  if(operatorConfirmed!==true)throw Error('An explicit operator confirmation is required.');
  if(!label(operatorId)||!iso(reviewedAt)||
    !Number.isInteger(leaseHours)||leaseHours<1||leaseHours>168)
    throw Error('Invalid operator identity, review date, or inspection lease.');
  if(!validateEnrollmentRegistry(registry))throw Error('Enrollment registry invalid.');
  const report=verifySignedObject(signed,trustStore);
  if(report.signatureValid!==true||report.sourceReplayConsistent!==true||report.keyPinned!==true)
    throw Error('Cannot enroll: pinned-key R10 source verification failed.');
  const envelopeSha256=signedEnvelopeDigest(signed);
  const enrollmentId=hash({issuerId:signed.issuerId,keyId:signed.keyId,
    envelopeSha256,scope:signed.passport.scope});
  if(registry.entries.some(e=>e.enrollmentId===enrollmentId))
    throw Error('An enrollment already exists for this exact envelope. Revoke first; do not silently renew.');
  if(registry.entries.length>=MAX_ENTRIES)throw Error('Registry at maximum capacity.');
  const expiresAt=new Date(Date.parse(reviewedAt)+leaseHours*3600_000).toISOString();
  const entry={enrollmentId,envelopeSha256,issuerId:signed.issuerId,
    keyId:signed.keyId,model:signed.passport.subject.model,
    scope:signed.passport.scope,operatorId,reviewedAt,expiresAt,state:'APPROVED_INSPECTION'};
  const next={format:ENROLLMENT_FORMAT,entries:[...registry.entries,entry]};
  if(!validateEnrollmentRegistry(next))throw Error('Generated registry failed validation.');
  return next;
}
/** Revocations are terminal for a given envelope fingerprint. */
export function revokeEnrollment(registry,enrollmentId,operatorId,operatorConfirmed=false){
  if(operatorConfirmed!==true||!label(operatorId)||!digest(enrollmentId))
    throw Error('Explicit operator revocation confirmation and IDs required.');
  if(!validateEnrollmentRegistry(registry))throw Error('Invalid enrollment registry.');
  const index=registry.entries.findIndex(e=>e.enrollmentId===enrollmentId);
  if(index<0)throw Error('No matching enrollment.');
  if(registry.entries[index].state==='REVOKED')throw Error('Enrollment already revoked.');
  const next={format:ENROLLMENT_FORMAT,entries:registry.entries.map((e,i)=>
    i===index?{...e,state:'REVOKED'}:e)};
  if(!validateEnrollmentRegistry(next))throw Error('Revocation validation failed.');
  return next;
}
/**
 * Pure evaluation: signed data + pinned key + exact local registry + current clock.
 * Success means human inspection enrollment ONLY. Never usable as tool ACL.
 */
export function evaluateEnrollment(signed,trustStore,registry,now=new Date().toISOString()){
  if(!iso(now))return verdict('INVALID_CLOCK','Explicit bounded ISO clock required.');
  let report;
  try{report=verifySignedObject(signed,trustStore);}
  catch{return verdict('SIGNATURE_REJECTED','Signed evidence could not be verified.');}
  if(!report.signatureValid||!report.sourceReplayConsistent||!report.keyPinned)
    return verdict('SIGNATURE_REJECTED',report.reason);
  if(!validateEnrollmentRegistry(registry))
    return verdict('REGISTRY_REJECTED','No valid receiver-local enrollment registry.',true);
  const envelopeSha256=signedEnvelopeDigest(signed);
  const enrollmentId=hash({issuerId:signed.issuerId,keyId:signed.keyId,
    envelopeSha256,scope:signed.passport.scope});
  const entry=registry.entries.find(e=>e.enrollmentId===enrollmentId);
  if(!entry)return verdict('NOT_ENROLLED','Signature verified; receiver has not approved inspection of this envelope.',true);
  if(entry.state==='REVOKED')return verdict('REVOKED','Operator revoked this enrollment.',true);
  if(entry.envelopeSha256!==envelopeSha256||entry.issuerId!==signed.issuerId||
    entry.keyId!==signed.keyId||entry.model!==signed.passport.subject.model||
    entry.scope!==signed.passport.scope)
    return verdict('REGISTRY_REJECTED','Enrollment binding mismatch.',true);
  const clock=Date.parse(now);
  if(clock<Date.parse(entry.reviewedAt))return verdict('NOT_YET_VALID','Enrollment review time is in the future.',true);
  if(clock>=Date.parse(entry.expiresAt))return verdict('EXPIRED','Receiver-local inspection lease expired.',true);
  return verdict('APPROVED_FOR_INSPECTION_ONLY',
    'Pinned signature and R6 replay verified; operator approved bounded evidence inspection only. No real-world action permission.',true,true);
}
