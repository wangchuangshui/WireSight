/* Showcase the frozen point coordinates. This page never calls an annotator. */
(() => {
const D=window.WIRE_DEMO,$=id=>document.getElementById(id);const payload=window.ANNOTATION_POINTS[D.overview.run_id];let viewer,rotate=true,near=true,last=0,visible=true;
try{const bytes=Uint8Array.from(atob(payload.data),c=>c.charCodeAt(0));viewer=new WirePointView($('hero-canvas'),new Float32Array(bytes.buffer),D.overview);viewer.region([94,118]);viewer.yaw=-.55;viewer.pitch=-.55;viewer.draw();}
catch(e){$('hero-canvas').replaceWith(Object.assign(document.createElement('p'),{textContent:'3D is unavailable in this browser; inspect the projections or film below.'}));}
function setMode(on){if(!viewer)return;viewer.annotated=on;viewer.draw();$('hero-colored').classList.toggle('active',on);$('hero-plain').classList.toggle('active',!on);}
function stop(){rotate=false;$('hero-spin').textContent='Resume rotation';}
$('hero-plain').onclick=()=>setMode(false);$('hero-colored').onclick=()=>setMode(true);
$('hero-region').onclick=()=>{near=!near;if(near){viewer?.region([94,118]);if(viewer){viewer.yaw=-.55;viewer.pitch=-.55;viewer.draw();}}else{viewer?.select(0);viewer?.preset('oblique');}$('hero-scope').textContent=near?'Tower close-up / Y94–118m':'Full scene / five main wires';$('hero-region').textContent=near?'Full scene ↗':'Tower close-up ↗';};
$('hero-spin').onclick=()=>{rotate=!rotate;$('hero-spin').textContent=rotate?'Pause rotation':'Resume rotation';};
$('hero-canvas')?.addEventListener('pointerdown',stop);if($('hero-canvas'))new IntersectionObserver(entries=>{visible=entries[0].isIntersecting}).observe($('hero-canvas'));if(matchMedia('(prefers-reduced-motion: reduce)').matches)stop();
function loop(t){if(viewer&&rotate&&visible&&!document.hidden&&t-last>60){viewer.yaw+=.0025;viewer.draw();last=t;}requestAnimationFrame(loop)}requestAnimationFrame(loop);
$('open-film').onclick=()=>{$('film-dialog').showModal();$('film-player').play().catch(()=>{})};$('close-film').onclick=()=>{$('film-player').pause();$('film-dialog').close()};$('film-dialog').addEventListener('close',()=>$('film-player').pause());
for(const a of document.querySelectorAll('[data-jump]'))a.onclick=()=>{window.WireDemo.stop();window.WireDemo.show(Number(a.dataset.jump))};
const overlay=$('model-path-overlay'),toggle=$('model-path-toggle');let pathsOn=false;
for(const row of window.RECORDED_TOP_SELECTIONS){const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',row.selection.coordinates.map(p=>p.join(',')).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke',D.overview.main_wires[row.id-1].color);line.setAttribute('stroke-width','5');line.dataset.sourceStep=String(row.step_index+1);overlay.append(line);}
toggle.onclick=()=>{pathsOn=!pathsOn;overlay.toggleAttribute('hidden',!pathsOn);toggle.textContent=pathsOn?'Hide paths / original image':'Overlay recorded model paths';$('input-footer').textContent=pathsOn?'Paths come from stored PROPOSE selections; they are not input labels and do not change the image or 3D annotation.':'Top view: XY positions, Z-dependent brightness; depth and IDs stay local.'};
window.onWireImageChange=(step,angle)=>{const eligible=step===0&&angle===0;toggle.hidden=!eligible;overlay.setAttribute('hidden','');pathsOn=false;toggle.textContent='Overlay recorded model paths';};
window.WireLaunch={viewer,stop,setMode};
})();
