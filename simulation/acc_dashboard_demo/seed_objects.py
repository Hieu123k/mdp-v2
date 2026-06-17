#!/usr/bin/env python3
"""Replace the prompt-23 seed function (seed_fn_p23) in a Node-RED flow array (stdin) with an expanded
seed that loads the 8 accounting demo objects (acc_*) per design SS1/SS4 (plus the existing sim_* objects).
Key VALUES are added at runtime (never committed) — objects only reference key labels. Output -> stdout."""
import sys, json

FN_ID = "seed_fn_p23"

SEED_FUNC = r"""// prompt 23 + 25: seed the demo objects so the /ui is reproducible. API key VALUES are added at runtime
// (never committed); objects only reference key labels. Idempotent: replaces these objects, preserves any
// others + all keys; resets their Seq counters so a fresh seed yields distinct dim ids.
let objects = flow.get("mdpsim_objects") || [];
const demo = [
  // --- prompt 23 sim demo (kept) ---
  {name:"sim_customer", model:"sim_customer", key:"sim_inbound_customer", attrs:[
    {name:"customer_id",type:"text",gen:"Seq",cfg:{start:1,seqstep:1}},
    {name:"customer_name",type:"text",gen:"Random",cfg:{template:"CUST-{seq}"}},
    {name:"region",type:"text",gen:"List",cfg:{values:"North, Central, South"}},
    {name:"segment",type:"text",gen:"List",cfg:{values:"SME, Enterprise, Retail"}},
    {name:"created_date",type:"date",gen:"Random",cfg:{daysback:365}}]},
  {name:"sim_invoice", model:"sim_invoice", key:"sim_inbound_invoice", attrs:[
    {name:"invoice_no",type:"text",gen:"Random",cfg:{template:"INV-{seq}"}},
    {name:"customer_id",type:"text",gen:"List",cfg:{values:"1,2,3,4,5,6,7,8,9,10"}},
    {name:"amount",type:"float",gen:"Random",cfg:{min:50,max:5000,step:0.01}},
    {name:"status",type:"text",gen:"List",cfg:{values:"open, paid, cancelled"}},
    {name:"issued_date",type:"date",gen:"Random",cfg:{daysback:90}},
    {name:"issued_at",type:"datetime",gen:"Random",cfg:{}}]},
  // --- prompt 25 accounting demo: 3 dims (Seq) + 5 facts (List FK) ---
  {name:"acc_customer", model:"acc_customer", key:"acc_in_acc_customer", attrs:[
    {name:"customer_id",type:"text",gen:"Seq",cfg:{start:1,seqstep:1}},
    {name:"customer_name",type:"text",gen:"Random",cfg:{template:"CUST-{seq}"}},
    {name:"region",type:"text",gen:"List",cfg:{values:"North, Central, South"}},
    {name:"segment",type:"text",gen:"List",cfg:{values:"SME, Enterprise, Retail"}}]},
  {name:"acc_vendor", model:"acc_vendor", key:"acc_in_acc_vendor", attrs:[
    {name:"vendor_id",type:"text",gen:"Seq",cfg:{start:1,seqstep:1}},
    {name:"vendor_name",type:"text",gen:"Random",cfg:{template:"VEND-{seq}"}},
    {name:"category",type:"text",gen:"List",cfg:{values:"Material, Logistics, Service, Utility"}}]},
  {name:"acc_account", model:"acc_account", key:"acc_in_acc_account", attrs:[
    {name:"account_id",type:"text",gen:"Seq",cfg:{start:1,seqstep:1}},
    {name:"account_name",type:"text",gen:"Random",cfg:{template:"ACC-{seq}"}},
    {name:"account_type",type:"text",gen:"List",cfg:{values:"Asset, Liability, Equity, Revenue, Expense"}}]},
  {name:"acc_invoice", model:"acc_invoice", key:"acc_in_acc_invoice", attrs:[
    {name:"invoice_no",type:"text",gen:"Random",cfg:{template:"INV-{seq}"}},
    {name:"customer_id",type:"text",gen:"List",cfg:{values:"1,2,3,4,5,6,7,8,9,10"}},
    {name:"issue_date",type:"date",gen:"Random",cfg:{daysback:120}},
    {name:"due_date",type:"date",gen:"Random",cfg:{daysback:90}},
    {name:"amount",type:"float",gen:"Random",cfg:{min:50,max:5000,step:0.01}},
    {name:"tax_amount",type:"float",gen:"Random",cfg:{min:0,max:500,step:0.01}},
    {name:"status",type:"text",gen:"List",cfg:{values:"open, paid, overdue, cancelled"}}]},
  {name:"acc_receipt", model:"acc_receipt", key:"acc_in_acc_receipt", attrs:[
    {name:"receipt_no",type:"text",gen:"Random",cfg:{template:"RCP-{seq}"}},
    {name:"customer_id",type:"text",gen:"List",cfg:{values:"1,2,3,4,5,6,7,8,9,10"}},
    {name:"receipt_date",type:"date",gen:"Random",cfg:{daysback:90}},
    {name:"amount",type:"float",gen:"Random",cfg:{min:50,max:5000,step:0.01}},
    {name:"method",type:"text",gen:"List",cfg:{values:"cash, bank, card"}}]},
  {name:"acc_bill", model:"acc_bill", key:"acc_in_acc_bill", attrs:[
    {name:"bill_no",type:"text",gen:"Random",cfg:{template:"BILL-{seq}"}},
    {name:"vendor_id",type:"text",gen:"List",cfg:{values:"1,2,3,4,5,6,7,8"}},
    {name:"issue_date",type:"date",gen:"Random",cfg:{daysback:120}},
    {name:"due_date",type:"date",gen:"Random",cfg:{daysback:90}},
    {name:"amount",type:"float",gen:"Random",cfg:{min:30,max:4000,step:0.01}},
    {name:"status",type:"text",gen:"List",cfg:{values:"open, paid, overdue"}}]},
  {name:"acc_payment", model:"acc_payment", key:"acc_in_acc_payment", attrs:[
    {name:"payment_no",type:"text",gen:"Random",cfg:{template:"PAY-{seq}"}},
    {name:"vendor_id",type:"text",gen:"List",cfg:{values:"1,2,3,4,5,6,7,8"}},
    {name:"payment_date",type:"date",gen:"Random",cfg:{daysback:90}},
    {name:"amount",type:"float",gen:"Random",cfg:{min:30,max:4000,step:0.01}},
    {name:"method",type:"text",gen:"List",cfg:{values:"cash, bank"}}]},
  {name:"acc_journal", model:"acc_journal", key:"acc_in_acc_journal", attrs:[
    {name:"entry_id",type:"text",gen:"Random",cfg:{template:"JE-{seq}"}},
    {name:"account_id",type:"text",gen:"List",cfg:{values:"1,2,3,4,5,6,7,8"}},
    {name:"entry_date",type:"date",gen:"Random",cfg:{daysback:120}},
    {name:"debit",type:"float",gen:"Random",cfg:{min:0,max:3000,step:0.01}},
    {name:"credit",type:"float",gen:"Random",cfg:{min:0,max:3000,step:0.01}},
    {name:"doc_ref",type:"text",gen:"Random",cfg:{template:"DOC-{seq}"}}]}
];
const names = demo.map(o=>o.name);
objects = objects.filter(o=>!names.includes(o.name)).concat(demo);
flow.set("mdpsim_objects", objects);
let ctr = flow.get("mdpsim_seqctr") || {};
Object.keys(ctr).forEach(k=>{ if(names.some(n=>k.indexOf(n+"|")===0)) delete ctr[k]; });
flow.set("mdpsim_seqctr", ctr);
const keys = flow.get("mdpsim_keys") || [];
node.status({fill:"green",shape:"dot",text:"seeded "+demo.length+" demo objects @ "+new Date(Date.now()+25200000).toISOString().slice(11,19)});
return {topic:"state", payload:{objects, keys}};
"""

flows = json.load(sys.stdin)
if isinstance(flows, dict):
    flows = flows.get("flows", flows)
for n in flows:
    if n.get("id") == FN_ID:
        n["func"] = SEED_FUNC
json.dump(flows, sys.stdout, indent=4, ensure_ascii=False)
