(() => {
  const form = document.querySelector("#trip-form");
  if (!form) return;
  const storage = window.STPStorage;
  const serviceNames = { brindisi:"Urbano Brindisi", extraurbano:"Extraurbano", ostuni:"Urbano Ostuni", francavilla:"Urbano Francavilla" };

  function createField(side) {
    const input = document.querySelector(`#${side}-label`);
    const hidden = document.querySelector(`#${side}-point`);
    const panel = input.parentElement.querySelector(".suggestions");
    let timer, requestId = 0;

    function select(item) {
      const point = {
        type:item.type, name:item.name || item.stop_name,
        lat:Number(item.lat ?? item.stop_lat), lon:Number(item.lon ?? item.stop_lon),
        stop_key:item.stop_key || (item.stop_id ? `${item.feed_id}:${item.stop_id}` : null)
      };
      input.value = point.name; hidden.value = JSON.stringify(point); panel.hidden = true;
      input.classList.add("selected");
    }
    function addGroup(title, items, detail) {
      if (!items.length) return;
      const heading = document.createElement("p"); heading.className="suggestion-heading"; heading.textContent=title; panel.append(heading);
      items.forEach(item => {
        const button=document.createElement("button"); button.type="button";
        const strong=document.createElement("strong"); strong.textContent=item.name || item.stop_name;
        const small=document.createElement("small"); small.textContent=detail(item);
        button.append(strong,small); button.addEventListener("click",()=>select(item)); panel.append(button);
      });
    }
    async function search(query) {
      const id=++requestId;
      const saved=[...(storage?.read("stpCustomPlaces",[])||[]).map(x=>({...x,type:"saved"})), ...(storage?.read("stpFavoriteStops",[])||[]).map(x=>({...x,type:"stop",stop_key:x.key}))]
        .filter(x=>x.name.toLowerCase().includes(query.toLowerCase())).slice(0,5);
      try {
        const [placesResponse,stopsResponse]=await Promise.all([
          fetch(`/api/places?q=${encodeURIComponent(query)}`), fetch(`/api/stops?q=${encodeURIComponent(query)}&limit=15`)
        ]);
        if(id!==requestId)return;
        const places=placesResponse.ok?await placesResponse.json():[];
        const stops=stopsResponse.ok?await stopsResponse.json():[];
        panel.replaceChildren();
        addGroup("Luoghi salvati",saved,()=>"Salvato sul dispositivo");
        addGroup("Posizioni e indirizzi",places,item=>item.category||"Posizione");
        addGroup("Fermate STP",stops,item=>serviceNames[item.feed_id]||item.feed_id);
        if(!saved.length&&!places.length&&!stops.length){const empty=document.createElement("p");empty.className="suggestion-empty";empty.textContent="Nessun risultato. Prova a specificare città o indirizzo.";panel.append(empty);}
        panel.hidden=false;
      } catch { panel.hidden=true; }
    }
    input.addEventListener("input",()=>{
      hidden.value="";input.classList.remove("selected");clearTimeout(timer);
      const query=input.value.trim();if(query.length<3){panel.hidden=true;return;}timer=setTimeout(()=>search(query),280);
    });
    document.addEventListener("click",event=>{if(!input.parentElement.contains(event.target))panel.hidden=true;});
    return {input,hidden,panel,select};
  }

  const from=createField("from"),to=createField("to");
  document.querySelector("#swap")?.addEventListener("click",()=>{
    [from.input.value,to.input.value]=[to.input.value,from.input.value];
    [from.hidden.value,to.hidden.value]=[to.hidden.value,from.hidden.value];
  });

  document.querySelectorAll("[data-use-location]").forEach(button=>button.addEventListener("click",()=>{
    const field=button.dataset.useLocation==="to"?to:from;
    if(!navigator.geolocation)return showError("Il browser non supporta la posizione.");
    button.disabled=true;button.textContent="Localizzazione…";
    navigator.geolocation.getCurrentPosition(position=>{
      field.select({type:"current",name:"Mia posizione",lat:position.coords.latitude,lon:position.coords.longitude});
      button.disabled=false;button.textContent="◎ Mia posizione";
    },()=>{button.disabled=false;button.textContent="◎ Mia posizione";showError("Posizione non disponibile. Controlla i permessi del browser.");},{enableHighAccuracy:true,timeout:12000});
  }));

  let pickerMap,pickerMarker,pickerField;
  const picker=document.querySelector("#map-picker");
  function openPicker(field){
    pickerField=field;picker.hidden=false;
    setTimeout(()=>{
      if(!pickerMap){pickerMap=L.map("picker-map").setView([40.6327,17.9418],13);L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(pickerMap);pickerMap.on("click",event=>{if(pickerMarker)pickerMarker.remove();pickerMarker=L.marker(event.latlng).addTo(pickerMap);});}
      pickerMap.invalidateSize();
    },20);
  }
  document.querySelectorAll("[data-pick-map]").forEach(button=>button.addEventListener("click",()=>openPicker(button.dataset.pickMap==="to"?to:from)));
  const closePicker=()=>{picker.hidden=true;};
  document.querySelector("#map-picker-close")?.addEventListener("click",closePicker);
  document.querySelector("#map-picker-confirm")?.addEventListener("click",()=>{
    if(!pickerMarker)return;
    const point=pickerMarker.getLatLng();pickerField.select({type:"map",name:"Punto scelto sulla mappa",lat:point.lat,lon:point.lng});closePicker();
  });

  function showError(message){document.querySelector("#form-error").textContent=message;}
  async function resolveRaw(field){
    if(field.hidden.value)return true;
    const query=field.input.value.trim();if(query.length<3)return false;
    const response=await fetch(`/api/places?q=${encodeURIComponent(query)}`);const items=response.ok?await response.json():[];
    if(items.length){field.select(items[0]);return true;}return false;
  }
  let submitting=false;
  form.addEventListener("submit",async event=>{
    if(submitting)return;
    event.preventDefault();showError("Ricerca delle posizioni…");
    try{
      const valid=(await resolveRaw(from))&&(await resolveRaw(to));
      if(!valid){showError("Non riesco a riconoscere una delle due posizioni. Scegli un suggerimento.");return;}
      const recent=storage?.read("stpRecentTrips",[])||[];
      const item={from:JSON.parse(from.hidden.value),to:JSON.parse(to.hidden.value)};
      const filtered=recent.filter(x=>x.from.name!==item.from.name||x.to.name!==item.to.name);storage?.write("stpRecentTrips",[item,...filtered].slice(0,5));
      submitting=true;showError("Calcolo del percorso e delle coincidenze…");
      const submit=form.querySelector("button[type=submit]");submit.disabled=true;submit.textContent="Sto cercando il percorso migliore…";form.classList.add("loading");form.submit();
    }catch{showError("Si è verificato un problema durante la ricerca.");}
  });

  const recent=storage?.read("stpRecentTrips",[])||[];
  const recentSection=document.querySelector("#recent-searches"),recentList=document.querySelector("#recent-search-list");
  if(recent.length&&recentSection&&recentList){recentSection.hidden=false;recent.forEach(item=>{const button=document.createElement("button");button.type="button";button.textContent=`${item.from.name} → ${item.to.name}`;button.addEventListener("click",()=>{from.select(item.from);to.select(item.to);location.hash="planner";});recentList.append(button);});}

  const params=new URLSearchParams(location.search);
  for(const [field,prefix] of [[from,"from"],[to,"to"]]){
    const key=params.get(`${prefix}_stop`),name=params.get(`${prefix}_name`);
    const hasCoordinates=params.has(`${prefix}_lat`)&&params.has(`${prefix}_lon`);
    const lat=Number(params.get(`${prefix}_lat`)),lon=Number(params.get(`${prefix}_lon`));
    if(key&&name&&hasCoordinates&&Number.isFinite(lat)&&Number.isFinite(lon)) field.select({type:"stop",name,lat,lon,stop_key:key});
    else if(key&&name){
      const favorite=(storage?.read("stpFavoriteStops",[])||[]).find(x=>x.key===key);
      if(favorite)field.select({...favorite,type:"stop",stop_key:key});
    }
  }
})();
