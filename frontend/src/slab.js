export function slabGeometry(record, factor=1) {
  const defaults={length:10000,width:1400,thickness:230}, values={}, fallback=[]
  for(const key of Object.keys(defaults)) {
    const v=Number(record?.[key])
    values[key]=Number.isFinite(v)&&v>0?v:defaults[key]
    if(!Number.isFinite(v)||v<=0)fallback.push(key)
  }
  return {values, fallback, x:values.length/1000, y:values.thickness/1000*factor, z:values.width/1000, factor}
}
export function colorFor(value, scale) {
  if(value==null||!scale||!Number.isFinite(Number(value)))return '#778394'
  const stops=[[50,105,149],[65,162,189],[236,202,100],[217,130,64]]
  const t=scale.max===scale.min ? 0.5 :Math.max(0,Math.min(1,(value-scale.min)/(scale.max-scale.min)))
  const pos=t*(stops.length-1),i=Math.min(stops.length-2,Math.floor(pos)),w=pos-i
  return '#'+stops[i].map((v,c)=>Math.round(v+(stops[i+1][c]-v)*w).toString(16).padStart(2,'0')).join('')
}
