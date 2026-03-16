function extractPageText(){
    return document.body.innerText;
}

function analyzeText(text){

fetch("http://localhost:8000/analyze", {
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({text:text})
})
.then(res=>res.json())
.then(data=>{
showWarning(data);
})
.catch(err=>{
console.log("Backend not running");
});

}

function showWarning(data){

if(data.risk > 0.7){

alert(
"⚠️ Scam Warning\n\n"+
"Risk Score: "+data.risk+"\n"+
"Reason: "+data.reason
);

}

}

setTimeout(()=>{
let text = extractPageText();
analyzeText(text);
},3000);
