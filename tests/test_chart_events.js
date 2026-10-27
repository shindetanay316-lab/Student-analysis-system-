const fs=require('fs'),vm=require('vm'),assert=require('assert');
const data={sgpa_distribution:[{key:'4',label:'8–8.99',count:3}],result_status:[{key:'PASS',label:'Pass',count:3}],validation_status:[{key:'WARNING',label:'Warning',count:1}],grade_distribution:[{grade:'BB',count:4}],component_performance:[{key:'ESE',component:'Ese',average_percentage:80}],subject_performance:[{code:'S1',name:'Full Subject Name',average_percentage:80,pass_rate:100}]};
const charts={},elements={},navigation=[];
for(const id of ['sgpaChart','resultStatusChart','subjectChart','validationChart','gradeChart','componentChart'])elements[id]={id};
elements['analysis-data']={textContent:JSON.stringify(data)};
elements['analysis-links']={dataset:{recordsUrl:'/result-data/analysis/imports/7/records'}};
function Chart(element,config){charts[element.id]=config}
Chart.defaults={font:{},animation:{},plugins:{legend:{labels:{}}}};
const document={documentElement:{},body:{},getElementById:id=>elements[id],addEventListener:(type,fn)=>fn()};
const window={location:{origin:'http://localhost',assign:url=>navigation.push(new URL(url))},matchMedia:()=>({matches:false})};
const context={document,window,Chart,URL,getComputedStyle:()=>({getPropertyValue:()=> '#123456',fontFamily:'Arial'})};
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../static/result_data/js/analysis.js'),'utf8'),context);
const cases=[['sgpaChart','sgpa','4'],['resultStatusChart','result','PASS'],['validationChart','validation','WARNING'],['gradeChart','grade','BB'],['componentChart','component','ESE'],['subjectChart','subject','S1']];
for(const [id,kind,value] of cases){
 charts[id].options.onClick({},[{index:0,datasetIndex:0}]);const url=navigation.at(-1);
 assert.equal(url.searchParams.get('kind'),kind);assert.equal(url.searchParams.get('value'),value);
 assert.equal(url.pathname,'/result-data/analysis/imports/7/records');
}
charts.subjectChart.options.onClick({},[{index:0,datasetIndex:1}]);assert.equal(navigation.at(-1).searchParams.get('outcome'),'PASS');
assert.equal(charts.subjectChart.data.labels[0],'Full Subject Name');
for(const id of ['resultStatusChart','validationChart']){charts[id].options.plugins.legend.onClick({}, {index:0});assert(navigation.at(-1).searchParams.get('value'))}
const before=navigation.length;charts.sgpaChart.options.onClick({},[]);assert.equal(navigation.length,before);
console.log('PASS: all six chart clicks, subject dataset selection, legend filters, full subject labels and empty-area clicks.');
