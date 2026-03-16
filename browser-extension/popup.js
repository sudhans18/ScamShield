document.getElementById("scanBtn").addEventListener("click",function(){

chrome.tabs.query({active:true,currentWindow:true},function(tabs){

chrome.scripting.executeScript({
target:{tabId:tabs[0].id},
function:scanPage
});

});

});

function scanPage(){

let text = document.body.innerText;

fetch("http://localhost:8000/analyze",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({text:text})
})
.then(res=>res.json())
.then(data=>{

alert(
"Risk Score: "+data.risk+"\n"+
"Reason: "+data.reason
);

});

}