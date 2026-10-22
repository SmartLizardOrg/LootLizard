/** Only user-selected map references are persisted, never captured frames. */
const DATABASE = 'lootlizard-browser-poc';
async function database() {
  return new Promise((resolve,reject) => {
    const request=indexedDB.open(DATABASE,1);
    request.onupgradeneeded=()=>request.result.createObjectStore('references',{keyPath:'mapId'});
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
  });
}
export async function referenceStore(mode,value) {
  const db=await database();
  try { return await new Promise((resolve,reject)=>{
    const tx=db.transaction('references',mode==='read'?'readonly':'readwrite');
    const store=tx.objectStore('references'); let result;
    if(mode==='read') {const request=store.getAll();request.onsuccess=()=>{result=request.result;};}
    else if(mode==='put') store.put(value);
    else if(mode==='clear') store.clear();
    else {reject(Error('Unknown reference-store operation'));return;}
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
  }); } finally {db.close();}
}
