/* Exercise the shipped UI handlers without requiring a browser installation. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
class Element {
    constructor() { this.children=[]; this.listeners={}; this.value=''; this.hidden=false; this.disabled=false; this.textContent=''; }
    get options() { return this.children; }
    appendChild(child) { this.children.push(child); }
    replaceChildren(...children) { this.children=children; }
    addEventListener(type,handler) { this.listeners[type]=handler; }
    fire(type) { this.listeners[type](); }
    querySelector() { return this.body; }
}
const ids=['subject','subject-search','subject-search-status','assignment-roster-data','roster-table','roster-status','academic-year','semester','assign-button','context-change-message'];
const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
elements['roster-table'].body=new Element();
elements['academic-year'].value='2025-26';elements.semester.value='6';
for (const [value,text] of [['','Select a subject'],['TH601','Theory Subject (TH601)'],['LB601','Lab Subject (LB601)'],['EL601A','Elective A (EL601A)']]) {
    const option=new Element();option.value=value;option.textContent=text;elements.subject.appendChild(option);
}
elements['assignment-roster-data'].textContent=JSON.stringify({TH601:[{cohort:2023,division:'A',batch:'A1',count:2},{cohort:2024,division:'B',batch:'B2',count:1}],LB601:[],EL601A:[]});
const document={getElementById:id=>elements[id],createElement:()=>new Element()};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/js/teacher_assignments.js'),'utf8'),{document});
elements['subject-search'].value='th601';elements['subject-search'].fire('input');
assert.deepEqual(elements.subject.options.map(option=>option.value),['','TH601']);
assert.ok(elements.subject.options.every(option=>!option.disabled));
elements.subject.value='TH601';elements.subject.fire('change');
assert.equal(elements['roster-table'].hidden,false);
assert.equal(elements['roster-table'].body.children.length,2);
assert.match(elements['roster-status'].textContent,/3 enrolled students/);
elements['subject-search'].value='missing';elements['subject-search'].fire('input');
assert.equal(elements.subject.options.length,1);assert.equal(elements.subject.value,'');
assert.match(elements.subject.options[0].textContent,/No subjects match/);
elements['subject-search'].value='';elements['subject-search'].fire('input');
assert.equal(elements.subject.options.length,4);
elements.subject.value='LB601';elements.subject.fire('change');
assert.match(elements['roster-status'].textContent,/No students are enrolled/);
elements['academic-year'].value='2026-27';elements['academic-year'].fire('input');
assert.equal(elements['assign-button'].disabled,true);
assert.equal(elements['context-change-message'].hidden,false);
elements['academic-year'].value='2025-26';elements['academic-year'].fire('input');
assert.equal(elements['assign-button'].disabled,false);
elements.semester.value='7';elements.semester.fire('change');
assert.equal(elements['assign-button'].disabled,true);
console.log('PASS: subject search, empty/reset results, cohort/group preview and stale context guard.');
