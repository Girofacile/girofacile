// Shared by desktop and both mobile delivery portals.
async function podPhotoPayload(required=false) {
  const file = document.getElementById('podDeliveryPhoto')?.files?.[0];
  if(!file) {
    if(required) throw Error('Scatta o seleziona la foto della consegna obbligatoria');
    return {};
  }
  if(!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 12000000)
    throw Error('Foto non valida: usa JPEG, PNG o WebP fino a 12 MB');
  const bitmap = await createImageBitmap(file);
  try {
    if(bitmap.width * bitmap.height > 24000000) throw Error('Foto troppo grande: massimo 24 megapixel');
    const scale = Math.min(1,1600/Math.max(bitmap.width,bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1,Math.round(bitmap.width*scale));
    canvas.height = Math.max(1,Math.round(bitmap.height*scale));
    const context = canvas.getContext('2d');
    context.fillStyle = '#fff'; context.fillRect(0,0,canvas.width,canvas.height);
    context.drawImage(bitmap,0,0,canvas.width,canvas.height);
    return {delivery_photo_data:canvas.toDataURL('image/jpeg',0.82)};
  } finally { bitmap.close(); }
}

function podEvidenceButtons(delivery, base) {
  return [['signature','has_signature','Visualizza firma'],['delivery_photo','has_delivery_photo','Visualizza foto'],['pod','has_pod','Scarica POD']]
    .filter(([,flag])=>delivery[flag]).map(([kind,,label])=>
      `<button type="button" class="btn-mini pod-evidence-action" onclick="podOpenEvidence('${base}/${kind}')">${label}</button>`).join(' ');
}

async function podOpenEvidence(path) {
  // Reserve the tab during the user gesture; fetch may finish after popup grace time.
  const target = window.open('about:blank','_blank');
  if(target) target.opener = null;
  try {
    const response = await fetch(path,{credentials:'same-origin',cache:'no-store'});
    if(!response.ok) {
      const error = await response.json();
      throw Error(error.detail || 'Documento non disponibile');
    }
    let url;
    if(response.headers.get('content-type')?.includes('application/json')) {
      url = (await response.json()).url;
    } else {
      url = URL.createObjectURL(await response.blob());
      setTimeout(()=>URL.revokeObjectURL(url),900000);
    }
    if(target) target.location.replace(url);
    else { const link=document.createElement('a'); link.href=url; link.target='_blank'; link.rel='noopener'; link.click(); }
  } catch(error) { target?.close(); alert(error.message); }
}
