(() => {
  const source=document.querySelector("#journeys-data"),mapNode=document.querySelector("#plan-map");
  if(!source||!mapNode||typeof L==="undefined")return;
  const journeys=JSON.parse(source.textContent);const map=L.map(mapNode,{scrollWheelZoom:false});
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"&copy; OpenStreetMap"}).addTo(map);
  let layer,token=0;
  const segmentPoints=segment=>segment.type==="walk"?[[segment.from_lat,segment.from_lon],[segment.to_lat,segment.to_lon]]:(segment.stops||[]).filter(x=>x.stop_lat&&x.stop_lon).map(x=>[x.stop_lat,x.stop_lon]);
  async function drawSegment(segment,target,emphasis=false,currentToken=token){
    const points=segmentPoints(segment);if(points.length<2)return points;
    if(segment.type==="walk"){L.polyline(points,{color:"#f59e0b",weight:emphasis?7:4,dashArray:"7 7",opacity:.9}).addTo(target);return points;}
    const fallback=L.polyline(points,{color:"#0284c7",weight:emphasis?7:5,opacity:.82,dashArray:"5 6"}).addTo(target);
    try{const road=await window.routeStopsOnRoad(segment.stops||[]);if(currentToken===token&&road.length){fallback.remove();L.polyline(road,{color:"#0284c7",weight:emphasis?7:5,opacity:.9}).addTo(target);return road;}}catch{}
    return points;
  }
  async function showOption(index,onlySegment=null){
    const currentToken=++token;if(layer)layer.remove();layer=L.layerGroup().addTo(map);const bounds=[];
    const segments=onlySegment===null?journeys[index].segments:[journeys[index].segments[onlySegment]];
    for(const segment of segments){const points=await drawSegment(segment,layer,onlySegment!==null,currentToken);bounds.push(...points);}
    if(currentToken!==token)return;
    if(bounds.length){L.marker(bounds[0]).bindPopup("Partenza").addTo(layer);L.marker(bounds[bounds.length-1]).bindPopup("Arrivo").addTo(layer);map.fitBounds(bounds,{padding:[28,28],maxZoom:16});}
  }
  document.querySelectorAll(".plan-option").forEach((option,index)=>{
    option.querySelector(".option-summary").addEventListener("click",()=>{document.querySelectorAll(".plan-option").forEach(x=>x.classList.remove("active"));option.classList.add("active");showOption(index);});
    option.querySelectorAll(".plan-step").forEach((step,segmentIndex)=>step.addEventListener("click",event=>{event.stopPropagation();showOption(index,segmentIndex);mapNode.scrollIntoView({behavior:"smooth",block:"center"});}));
  });
  showOption(0);setTimeout(()=>map.invalidateSize(),0);
})();
