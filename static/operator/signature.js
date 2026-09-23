// Signature input for the token-based portal; the server enforces the same rule.
let operatorSignatureDrawn = false;
const operatorCanvas = document.getElementById('operatorSignatureCanvas');
const operatorPen = operatorCanvas.getContext('2d');
operatorPen.lineWidth = 2;
operatorPen.lineCap = 'round';
let operatorDrawing = false;
function clearOperatorSignature(){
  operatorPen.clearRect(0, 0, operatorCanvas.width, operatorCanvas.height);
  operatorSignatureDrawn = false;
  document.getElementById('operatorSigner').value = '';
}
function operatorSignaturePoint(event){
  const bounds = operatorCanvas.getBoundingClientRect();
  return [(event.clientX-bounds.left)*operatorCanvas.width/bounds.width,
          (event.clientY-bounds.top)*operatorCanvas.height/bounds.height];
}
operatorCanvas.addEventListener('pointerdown', event=>{
  operatorDrawing = true;
  operatorCanvas.setPointerCapture(event.pointerId);
  operatorPen.beginPath();
  operatorPen.moveTo(...operatorSignaturePoint(event));
});
operatorCanvas.addEventListener('pointermove', event=>{
  if(!operatorDrawing) return;
  operatorPen.lineTo(...operatorSignaturePoint(event));
  operatorPen.stroke();
  operatorSignatureDrawn = true;
});
['pointerup','pointercancel','lostpointercapture'].forEach(name=>
  operatorCanvas.addEventListener(name, ()=>{operatorDrawing=false;}));

function operatorSignaturePayload(){
  if(!routeData.delivery_signature_enabled) return {};
  const name = document.getElementById('operatorSigner').value.trim();
  if(!operatorSignatureDrawn || !name) throw Error('Inserisci il nome del firmatario e raccogli la firma');
  return {signature_data:operatorCanvas.toDataURL('image/png'), signed_by_name:name};
}
