/**
 * R13 offline receiver witness for the R12 operator-signed inspection ledger.
 * A separate operator-pinned WITNESS signing key endorses an exact checkpoint.
 * This is not immutable storage, network notarization, model identity, skill,
 * authentication of source history, or ANY authorization to use tools.
 */
import {createHash,createPrivateKey,createPublicKey,sign,verify} from 'node:crypto';
import {verifyLedger,createCheckpoint,checkpointMatches,GENESIS,SCOPE} from './r12-governance.mjs';

export const WITNESS_FORMAT='philearn.r13.witness-receipt.v1';
export const WITNESS_TRUST_FORMAT='philearn.r13.witness-trust.v1';
export const WITNESS_DOMAIN='PHILEARN-R13-CHECKPOINT-WITNESS-V1';
const exact=(x,keys)=>x&&typeof x==='object'&&!Array.isArray(x)&&
  Object.keys(x).sort().join('|')===[...keys].sort().join('|');
const validId=x=>typeof x==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/.test(x);
const hex=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const keyId=x=>typeof x==='string'&&/^sha256:[a-f0-9]{64}$/.test(x);
const iso=x=>typeof x==='string'&&x.length<=40&&/^\d{4}-\d\d-\d\dT/.test(x)&&Number.isFinite(Date.parse(x));
const b64=x=>typeof x==='string'&&x.length<1200&&/^[A-Za-z0-9+/]+={0,2}$/.test(x)&&
  Buffer.from(x,'base64').toString('base64')===x;
const pKey=x=>x?.type==='public'?x:createPublicKey(x);
const privateKey=x=>x?.type==='private'?x:createPrivateKey(x);
const fingerprint=x=>{
  const p=pKey(x);
  if(p.asymmetricKeyType!=='ed25519')throw Error('Ed25519 witness key required.');
  return 'sha256:'+createHash('sha256').update(p.export({format:'der',type:'spki'})).digest('hex');
};
const message=body=>Buffer.from(WITNESS_DOMAIN+'\n'+JSON.stringify(body)+'\n','utf8');
const denied=(status,reason)=>({status,reason,witnessValid:false,chainValid:false,
  headAnchored:false,authority:'NONE',permissions:[],actionAllowed:false});

export function makeWitnessTrustRecord(witnessId,publicKey){
  if(!validId(witnessId))throw Error('Invalid witness identifier.');
  const p=pKey(publicKey);
  return {witnessId,keyId:fingerprint(p),publicKeySpkiBase64:
    p.export({format:'der',type:'spki'}).toString('base64'),active:true};
}
export function validateWitnessTrust(store,operatorStore=null){
  if(!exact(store,['format','witnesses'])||store.format!==WITNESS_TRUST_FORMAT||
    !Array.isArray(store.witnesses)||store.witnesses.length>32||
    Buffer.byteLength(JSON.stringify(store))>14000)return false;
  const used=new Set();
  const operatorIds=new Set(operatorStore?.operators?.map(o=>o.keyId)??[]);
  for(const w of store.witnesses){
    if(!exact(w,['witnessId','keyId','publicKeySpkiBase64','active'])||
      !validId(w.witnessId)||!keyId(w.keyId)||!b64(w.publicKeySpkiBase64)||
      typeof w.active!=='boolean'||operatorIds.has(w.keyId))return false;
    try{
      const p=createPublicKey({key:Buffer.from(w.publicKeySpkiBase64,'base64'),
        format:'der',type:'spki'});
      if(fingerprint(p)!==w.keyId)return false;
    }catch{return false;}
    const compound=w.witnessId+':'+w.keyId;
    if(used.has(compound))return false;
    used.add(compound);
  }
  return true;
}
export function witnessCheckpoint(ledger,operatorStore,witnessStore,
  witnessPrivate,witnessId,signedAt=new Date().toISOString()){
  if(!iso(signedAt))throw Error('Witness timestamp must be a bounded ISO8601 value.');
  const proof=verifyLedger(ledger,operatorStore);
  if(!proof.chainValid)throw Error('R12 chain invalid: '+proof.reason);
  const privateObject=privateKey(witnessPrivate);
  if(privateObject.asymmetricKeyType!=='ed25519')throw Error('Ed25519 witness private key required.');
  const id=fingerprint(createPublicKey(privateObject));
  if(!validateWitnessTrust(witnessStore,operatorStore)||
    witnessStore.witnesses.filter(w=>w.active&&w.witnessId===witnessId&&w.keyId===id).length!==1)
    throw Error('Separately pinned witness key required, distinct from all operator keys.');
  const last=ledger.entries.at(-1)?.event?.at;
  if(last&&Date.parse(signedAt)<Date.parse(last))throw Error('Witness cannot predate latest claimed event.');
  const body={format:WITNESS_FORMAT,witnessId,keyId:id,signedAt,scope:SCOPE,
    count:proof.eventCount,headHash:proof.headHash};
  return {...body,signature:sign(null,message(body),privateObject).toString('base64')};
}
/**
 * A MINIMUM previously witnessed count must be retained separately from the
 * mutable ledger and receipt. Old, genuinely signed heads otherwise can replay.
 */
export function verifyWitness(ledger,operatorStore,receipt,witnessStore,minimumCount=0){
  if(!Number.isSafeInteger(minimumCount)||minimumCount<0)
    return denied('INVALID_FLOOR','Receiver-protected minimum event count invalid.');
  const chain=verifyLedger(ledger,operatorStore);
  if(!chain.chainValid)return denied('CHAIN_INVALID',chain.reason);
  if(!validateWitnessTrust(witnessStore,operatorStore))
    return denied('WITNESS_TRUST_INVALID','Independent pinned witness registry missing or invalid.');
  if(!exact(receipt,['format','witnessId','keyId','signedAt','scope','count','headHash','signature'])||
    receipt.format!==WITNESS_FORMAT||!validId(receipt.witnessId)||!keyId(receipt.keyId)||
    !iso(receipt.signedAt)||receipt.scope!==SCOPE||
    !Number.isSafeInteger(receipt.count)||receipt.count<0||!hex(receipt.headHash)||
    !b64(receipt.signature)||Buffer.from(receipt.signature,'base64').length!==64)
    return denied('RECEIPT_INVALID','Malformed checkpoint witness receipt.');
  const found=witnessStore.witnesses.filter(w=>w.active&&w.witnessId===receipt.witnessId&&
    w.keyId===receipt.keyId);
  if(found.length!==1)return denied('WITNESS_UNPINNED','Witness not independently pinned or is revoked.');
  const signature=receipt.signature;
  const body={format:receipt.format,witnessId:receipt.witnessId,keyId:receipt.keyId,
    signedAt:receipt.signedAt,scope:receipt.scope,count:receipt.count,
    headHash:receipt.headHash};
  let valid=false;
  try{
    const p=createPublicKey({key:Buffer.from(found[0].publicKeySpkiBase64,'base64'),
      format:'der',type:'spki'});
    valid=verify(null,message(body),p,Buffer.from(signature,'base64'));
  }catch{/* invalid witness signature */}
  if(!valid)return denied('SIGNATURE_INVALID','Witness Ed25519 signature invalid.');
  const checkpoint={format:'philearn.r12.checkpoint.v1',
    count:receipt.count,headHash:receipt.headHash};
  if(!checkpointMatches(checkpoint,chain))
    return denied('HEAD_MISMATCH','Signed witness head does not match the full R12 chain.');
  if(receipt.count<minimumCount)
    return denied('ROLLBACK_BELOW_FLOOR','Witnessed event count is lower than independently retained floor.');
  const last=ledger.entries.at(-1)?.event?.at;
  if(last&&Date.parse(receipt.signedAt)<Date.parse(last))
    return denied('WITNESS_BEFORE_LAST_EVENT','Witness timestamp predates claimed final event.');
  return {status:'WITNESSED_HISTORY_NO_AUTHORITY',reason:'Operator event signatures, witness signature and full chain match. No action access granted.',
    witnessValid:true,chainValid:true,headAnchored:true,count:receipt.count,
    headHash:receipt.headHash,authority:'NONE',permissions:[],actionAllowed:false};
}
