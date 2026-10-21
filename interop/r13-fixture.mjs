/**
 * R13 TEST-ONLY cross-runtime fixture generator.
 * Deterministic seeded Ed25519 keys are PUBLIC TEST MATERIAL, never production secrets.
 * Output is a real complete R8/R10/R12/R13 signed JSON evidence chain.
 * Used byte-for-byte by Node and independent BrainC Python consumer tests.
 */
import {createHash,createPrivateKey,createPublicKey} from 'node:crypto';
import {CASES,FORMAT,CERT_PROTOCOL,CERT_SCOPE,R6,parseAction}
  from './skill-passport-verifier.mjs';
import {TRUST_FORMAT as R10_TRUST,createTrustRecord,createSignedPassport}
  from './r10-signed-passport.mjs';
import {
  TRUST_FORMAT as R12_TRUST,createOperatorRecord,emptyLedger,emptyCheckpoint,
  appendApproval,createCheckpoint,
} from './r12-governance.mjs';
import {
  WITNESS_TRUST_FORMAT,makeWitnessTrustRecord,witnessCheckpoint,
} from './r13-witness.mjs';

export const TEST_ONLY_SEEDS={
  issuer:'11'.repeat(32),operator:'22'.repeat(32),witness:'33'.repeat(32),
};
const keyFromSeed=(hex)=>{
  const der=Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),
    Buffer.from(hex,'hex')]);
  return createPrivateKey({key:der,format:'der',type:'pkcs8'});
};
const hash=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
const SOURCE_TIME='2026-10-21T20:00:00.000Z';
const SIGNED_TIME='2026-10-21T21:00:00.000Z';
const REVIEW_TIME='2026-10-21T22:00:00.000Z';
const WITNESS_TIME='2026-10-21T23:00:00.000Z';
export function makeFixture(){
  const issuerKey=keyFromSeed(TEST_ONLY_SEEDS.issuer),
    operatorKey=keyFromSeed(TEST_ONLY_SEEDS.operator),
    witnessKey=keyFromSeed(TEST_ONLY_SEEDS.witness);
  const model='TEST-ONLY:r13-synthetic',mode='guided';
  const episodes=CASES.map(s=>{
    const calls=[
      JSON.stringify({tool:'inspect',target:s.targets[0]}),
      JSON.stringify({tool:'inspect',target:s.targets[1]}),
      JSON.stringify({tool:'decide',decision:s.expected}),
    ];
    const steps=calls.map((raw,i)=>{
      const parsed=parseAction(raw);
      const reply=i<2?
        JSON.stringify({kind:'SYNTHETIC_INSPECTION',target:parsed.target,
          data:s.readings[parsed.target],effect:'read_only'}):
        JSON.stringify({kind:'SIMULATED_DECISION',value:s.expected,
          result:'Recorded for grading only. No external operation occurred.'});
      return {turn:i+1,raw,parsed,accepted:true,reply,latencyMs:12+i};
    });
    return {id:'r13-test-'+s.id,at:SOURCE_TIME,protocol:R6,provenance:'OBSERVED',
      scenarioId:s.id,model,mode,steps,outcome:'PASS',decision:s.expected};
  });
  const cert={id:'r13-test-only-cert',issuedAt:SOURCE_TIME,
    protocol:CERT_PROTOCOL,scope:CERT_SCOPE,provenance:'LOCAL_UNTRUSTED',model,mode,
    scenarioIds:CASES.map(s=>s.id),evidenceIds:episodes.map(e=>e.id),
    evidenceSha256:hash({protocol:CERT_PROTOCOL,scope:CERT_SCOPE,model,mode,episodes}),
    summary:'TEST ONLY: synthetic fixtures, fake history, no real authorization.',support:{}};
  const body={format:FORMAT,exportedAt:SOURCE_TIME,
    issuerClaim:{app:'PhiLearn',selfReported:true},
    subject:{model,mode},scope:CERT_SCOPE,
    boundary:{authority:'NONE',requestedPermissions:[],usage:'INSPECT_ONLY'},
    certificate:cert,episodes};
  const unsigned={...body,payloadSha256:hash(body)};
  const issuerTrust={format:R10_TRUST,
    keys:[createTrustRecord('TEST.issuer',createPublicKey(issuerKey))]};
  const signed=createSignedPassport(unsigned,issuerKey,'TEST.issuer',SIGNED_TIME);
  const operatorTrust={format:R12_TRUST,operators:[
    createOperatorRecord('TEST.operator',createPublicKey(operatorKey))]};
  const ledger=appendApproval(signed,issuerTrust,operatorTrust,emptyLedger(),
    operatorKey,'TEST.operator',REVIEW_TIME,24,true,emptyCheckpoint());
  const checkpoint=createCheckpoint(ledger,operatorTrust);
  const witnessTrust={format:WITNESS_TRUST_FORMAT,witnesses:[
    makeWitnessTrustRecord('TEST.witness',createPublicKey(witnessKey))]};
  const witness=witnessCheckpoint(ledger,operatorTrust,witnessTrust,
    witnessKey,'TEST.witness',WITNESS_TIME);
  return {purpose:'CROSS_RUNTIME_TEST_ONLY',source:'Node deterministic TEST seed; never a real audit',
    fixtureVersion:'philearn-r13-fixture-v1',signed,issuerTrust,operatorTrust,
    ledger,checkpoint,witnessTrust,witness,
    now:'2026-10-21T23:10:00.000Z',minimumCount:1};
}
if(process.argv[1]?.endsWith('r13-fixture.mjs'))
  process.stdout.write(JSON.stringify(makeFixture())+'\n');
