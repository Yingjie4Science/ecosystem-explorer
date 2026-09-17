// Generate bounded, approximate display statistics from raw categorical COG overviews.
// Run: node scripts/build-landcover-samples.mjs /path/to/temporary-geotiff-install
import {writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {fromUrl}=await import(pathToFileURL(process.argv[2]+'/node_modules/geotiff/dist-module/geotiff.js'));
const centers={shenzhen:[114.0579,22.5431],chengdu:[104.0668,30.5728],beijing:[116.4074,39.9042],shanghai:[121.4737,31.2304]};
const output={dataset:'ESA WorldCover 2021 v200',generated:new Date().toISOString(),method:'Nearest-neighbour sampling of raw categorical COG overviews on a 384x384 geographic grid per 2x2-degree demonstration extent. Not full-resolution zonal statistics.',cities:{}};
const width=384,height=384;
const cache=new Map();
for(const [key,[lon,lat]] of Object.entries(centers)){
  const bbox=[lon-1,lat-1,lon+1,lat+1],values=new Uint8Array(width*height),sources=[];
  for(let y=Math.floor(bbox[1]/3)*3;y<bbox[3];y+=3)for(let x=Math.floor(bbox[0]/3)*3;x<bbox[2];x+=3){
    const id=(y<0?'S':'N')+String(Math.abs(y)).padStart(2,'0')+(x<0?'W':'E')+String(Math.abs(x)).padStart(3,'0');
    const url='https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_'+id+'_Map.tif';
    sources.push(url);
    if(!cache.has(url))cache.set(url,fromUrl(url,{allowFullFile:false}));
    const tiff=await cache.get(url);
    const data=await tiff.readRasters({bbox,width,height,samples:[0],interleave:true,resampleMethod:'nearest',fillValue:0});
    for(let i=0;i<values.length;i++)if(data[i])values[i]=data[i];
  }
  output.cities[key]={bbox,width,height,sources,values:Buffer.from(values).toString('base64')};
  const counts={};for(const v of values)counts[v]=(counts[v]||0)+1;
  console.log(key,counts);
}
await writeFile(new URL('../dist/landcover-samples.json',import.meta.url),JSON.stringify(output));
