/**
 * R10: optional Ed25519 provenance on R8 Skill Passports.
 * No network, no agent execution, no implicit trust-on-first-use.
 * A verified signature authenticates control of one OPERATOR-PINNED KEY ONLY.
 */
import {createHash,createPrivateKey,createPublicKey,sign,verify} from 'node:crypto';
import {verifyObject} from './skill-passport-verifier.mjs';

export const SIGNED_FORMAT='philearn.signed-skill-passport.v1';
export const TRUST_FORMAT='philearn.r10.trust-store.v1';
export const DOMAIN='PHILEARN-R10-ED25519-SKILL-PASSPORT-V1';
export const SIGNED_MAX_BYTES=320_000;
const SCOPE='R6_SYNTHETIC_JSON_TOOL_GAUNTLET_6_CASES';
const isObj=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const exact=(x,keys)=>isObj(x)&&Object.keys(x).sort().join(',')===[...keys].sort().join(',');
const text=(x,max=160)=>typeof x==='string'&&x.length>0&&x.length<=max;
const sha=x=>createHash('sha256').update(x).digest('hex');
const isIso=x=>text(x,40)&&Number.isFinite(Date.parse(x))&&/^\d{4}-\d\d-\d\dT/.test(x);
const isB64=x=>typeof x==='string'&&x.length<1200&&/^[A-Za-z0-9+/]+={0,2}$/.test(x)&&
  Buffer.from(x,'base64').toString('base64')===x;
const msg=(issuerId,keyId,signedAt,payloadHash)=>
  Buffer.from([DOMAIN,issuerId,keyId,signedAt,payloadHash,''].join('\n'),'utf8');
const failed=(status,reason)=>({status,signatureValid:false,sourceReplayConsistent:false,
  keyPinned:false,operatorReview:'NOT_GRANTED',authority:'NONE',permissions:[],actionAllowed:false,reason});
function spki(publicKey){
  const key=publicKey?.type==='public'?publicKey:createPublicKey(publicKey);
  if(key.asymmetricKeyType!=='ed25519')throw Error('Only Ed25519 signing keys are supported.');
  return key.export({format:'der',type:'spki'});
}
export function keyFingerprint(publicKey){return 'sha256:'+sha(spki(publicKey));}
export function createTrustRecord(issuerId,publicKey){
  if(!text(issuerId,100)||!/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(issuerId))
    throw Error('Issuer ID must be a bounded ASCII label.');
  const keyDer=spki(publicKey);
  return {issuerId,keyId:'sha256:'+sha(keyDer),
    publicKeySpkiBase64:keyDer.toString('base64'),allowedScope:SCOPE,active:true};
}
export function createSignedPassport(passport,privatePem,issuerId,signedAt=new Date().toISOString()){
  if(!text(issuerId,100)||!/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(issuerId)||!isIso(signedAt))
    throw Error('Invalid issuer label or signing timestamp.');
  const base=verifyObject(passport);
  if(!base.replayConsistent)throw Error('Unsigned R8 passport must replay before signing: '+base.reason);
  const key=privatePem?.type==='private'?privatePem:createPrivateKey(privatePem);
  if(key.asymmetricKeyType!=='ed25519')throw Error('Only Ed25519 signing keys are supported.');
  const keyId=keyFingerprint(key);
  const body=msg(issuerId,keyId,signedAt,passport.payloadSha256);
  const signature=sign(null,body,key).toString('base64');
  const signed={format:SIGNED_FORMAT,algorithm:'Ed25519',issuerId,keyId,signedAt,
    passport,signature};
  if(Buffer.byteLength(JSON.stringify(signed))>SIGNED_MAX_BYTES)throw Error('Signed envelope too large.');
  return signed;
}
export function validateTrustStore(store){
  if(!exact(store,['format','keys'])||store.format!==TRUST_FORMAT||
    !Array.isArray(store.keys)||store.keys.length>40)return false;
  const ids=new Set();
  for(const key of store.keys){
    if(!exact(key,['issuerId','keyId','publicKeySpkiBase64','allowedScope','active'])||
      !text(key.issuerId,100)||!/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(key.issuerId)||
      !text(key.keyId,71)||!isB64(key.publicKeySpkiBase64)||
      key.allowedScope!==SCOPE||typeof key.active!=='boolean')return false;
    try{
      const publicKey=createPublicKey({key:Buffer.from(key.publicKeySpkiBase64,'base64'),
        format:'der',type:'spki'});
      if(key.keyId!==keyFingerprint(publicKey))return false;
    }catch{return false;}
    const id=key.issuerId+'\0'+key.keyId;
    if(ids.has(id))return false;
    ids.add(id);
  }
  return true;
}
/**
 * trustStore may ONLY come from an explicitly operator-supplied external file.
 * Not from this signed envelope. Review is separate human context, never permission.
 */
export function verifySignedObject(signed,trustStore=null,reviewAcknowledged=false){
  if(!exact(signed,['format','algorithm','issuerId','keyId','signedAt','passport','signature'])||
    signed.format!==SIGNED_FORMAT||signed.algorithm!=='Ed25519'||
    !text(signed.issuerId,100)||!/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(signed.issuerId)||
    !text(signed.keyId,71)||!/^sha256:[a-f0-9]{64}$/.test(signed.keyId)||
    !isIso(signed.signedAt)||!isB64(signed.signature)||
    Buffer.from(signed.signature,'base64').length!==64)
    return failed('REJECTED_SCHEMA','Unrecognized signed-envelope schema.');
  if(Buffer.byteLength(JSON.stringify(signed))>SIGNED_MAX_BYTES)
    return failed('REJECTED_SIZE','Signed envelope too large.');
  const baseline=verifyObject(signed.passport);
  if(!baseline.replayConsistent)
    return failed('REJECTED_REPLAY','R8 source traces or checksums failed: '+baseline.reason);
  if(!trustStore)return {
    ...failed('UNPINNED_SIGNATURE','Source replays, but no operator-pinned public key was supplied. Signature unverified.'),
    sourceReplayConsistent:true,
  };
  if(!validateTrustStore(trustStore))
    return failed('REJECTED_TRUST_STORE','Operator trust store malformed or invalid.');
  const matches=trustStore.keys.filter(key=>key.issuerId===signed.issuerId&&
    key.keyId===signed.keyId&&key.active&&key.allowedScope===signed.passport.scope);
  if(matches.length!==1)return {
    ...failed('UNPINNED_SIGNATURE','No matching active operator-pinned issuer/key for this scope.'),
    sourceReplayConsistent:true,
  };
  const pinned=matches[0];
  let valid=false;
  try{
    const key=createPublicKey({key:Buffer.from(pinned.publicKeySpkiBase64,'base64'),
      format:'der',type:'spki'});
    valid=verify(null,msg(signed.issuerId,signed.keyId,signed.signedAt,
      signed.passport.payloadSha256),key,Buffer.from(signed.signature,'base64'));
  }catch{return failed('SIGNATURE_INVALID','Pinned public-key signature could not be parsed.');}
  if(!valid)return {
    ...failed('SIGNATURE_INVALID','Signature does not authenticate the pinned key and payload.'),
    sourceReplayConsistent:true,keyPinned:true,
  };
  return {status:'SIGNATURE_VALID_PINNED_NO_AUTHORITY',
    signatureValid:true,sourceReplayConsistent:true,keyPinned:true,
    operatorReview:reviewAcknowledged?'ACKNOWLEDGED_FOR_INSPECTION':'NOT_GRANTED',
    authority:'NONE',permissions:[],actionAllowed:false,
    reason:'Ed25519 signature verified against an operator-pinned key; R8 traces replay. No actions, permissions, or source-truth claims granted.'};
}
export function verifySignedText(raw,trustStore=null,reviewAcknowledged=false){
  if(typeof raw!=='string'||Buffer.byteLength(raw)>SIGNED_MAX_BYTES)
    return failed('REJECTED_SIZE','Input is not a bounded UTF-8 string.');
  try{return verifySignedObject(JSON.parse(raw),trustStore,reviewAcknowledged);}
  catch{return failed('REJECTED_JSON','Malformed JSON or evidence.');}
}
