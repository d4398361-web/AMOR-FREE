/* AMOR HOSTING - 3D scene (three.js). Safe: silently skipped if WebGL is unavailable. */
(function(){
  var el=document.getElementById('scene'); if(!el||!window.THREE) return;
  var T=THREE, mode=(window.SCENE_MODE||'hero');
  var renderer; try{ renderer=new T.WebGLRenderer({alpha:true,antialias:true}); }catch(e){ return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio,2)); renderer.setSize(innerWidth,innerHeight); el.appendChild(renderer.domElement);
  var scene=new T.Scene(), cam=new T.PerspectiveCamera(55,innerWidth/innerHeight,.1,200); cam.position.set(0,0,mode==='hero'?15:20);
  var root=new T.Group(); scene.add(root);
  if(mode!=='hero') root.position.x=0, root.scale.setScalar(.85);

  // core crystal
  var core=new T.Mesh(new T.IcosahedronGeometry(2.3,1),new T.MeshBasicMaterial({color:0x8b5cf6,wireframe:true,transparent:true,opacity:.55}));
  var inner=new T.Mesh(new T.IcosahedronGeometry(1.5,0),new T.MeshBasicMaterial({color:0x22d3ee,transparent:true,opacity:.22}));
  var glow=new T.Mesh(new T.SphereGeometry(.7,24,24),new T.MeshBasicMaterial({color:0xf472b6,transparent:true,opacity:.85}));
  root.add(core,inner,glow);

  // orbit rings
  var rings=[]; [[4,.012,0x22d3ee,1.2],[5.6,.012,0x8b5cf6,.4],[7.2,.01,0xf472b6,-.8]].forEach(function(r,i){
    var m=new T.Mesh(new T.TorusGeometry(r[0],r[1],8,180),new T.MeshBasicMaterial({color:r[2],transparent:true,opacity:.6}));
    m.rotation.x=Math.PI/2+r[3]*.35; m.rotation.y=i*.6; root.add(m); rings.push(m);
  });

  // server blocks orbiting
  var servers=[], boxGeo=new T.BoxGeometry(.75,1.05,.75), edgeGeo=new T.EdgesGeometry(boxGeo);
  for(var i=0;i<22;i++){
    var g=new T.Group(), col=[0x22d3ee,0x8b5cf6,0xf472b6][i%3];
    g.add(new T.Mesh(boxGeo,new T.MeshBasicMaterial({color:0x0b0720,transparent:true,opacity:.85})));
    g.add(new T.LineSegments(edgeGeo,new T.LineBasicMaterial({color:col})));
    var led=new T.Mesh(new T.BoxGeometry(.5,.05,.02),new T.MeshBasicMaterial({color:0x34d399})); led.position.set(0,.3-.2*(i%3),.39); g.add(led);
    g.userData={r:4+(i%3)*1.6+Math.random()*.5,a:Math.random()*6.28,s:(.12+Math.random()*.18)*(i%2?1:-1),y:(Math.random()-.5)*3.2,p:Math.random()*6};
    root.add(g); servers.push(g);
  }

  // stars
  var N=1400, pos=new Float32Array(N*3);
  for(var j=0;j<N;j++){var r=25+Math.random()*60,t=Math.random()*6.28,p=Math.acos(2*Math.random()-1);
    pos[j*3]=r*Math.sin(p)*Math.cos(t);pos[j*3+1]=r*Math.sin(p)*Math.sin(t);pos[j*3+2]=r*Math.cos(p);}
  var sg=new T.BufferGeometry(); sg.setAttribute('position',new T.BufferAttribute(pos,3));
  var stars=new T.Points(sg,new T.PointsMaterial({color:0xbfb5ff,size:.12,transparent:true,opacity:.8})); scene.add(stars);

  var mx=0,my=0,sy=0,clock=new T.Clock();
  addEventListener('pointermove',function(e){mx=(e.clientX/innerWidth-.5)*2;my=(e.clientY/innerHeight-.5)*2;});
  addEventListener('scroll',function(){sy=scrollY/Math.max(1,document.body.scrollHeight-innerHeight);},{passive:true});
  addEventListener('resize',function(){cam.aspect=innerWidth/innerHeight;cam.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});

  function frame(){
    var t=clock.getElapsedTime();
    core.rotation.y=t*.25; core.rotation.x=t*.12; inner.rotation.y=-t*.3; glow.scale.setScalar(1+Math.sin(t*2)*.12);
    rings.forEach(function(r,i){r.rotation.z=t*(.1+i*.07)*(i%2?-1:1);});
    servers.forEach(function(s){var d=s.userData,a=d.a+t*d.s;
      s.position.set(Math.cos(a)*d.r,d.y+Math.sin(t+d.p)*.25,Math.sin(a)*d.r); s.rotation.y=-a; s.rotation.x=Math.sin(t*.5+d.p)*.2;});
    stars.rotation.y=t*.01;
    // parallax + scroll-driven camera
    root.rotation.y+=((mx*.5)-root.rotation.y)*.04; root.rotation.x+=((my*.25+sy*1.2)-root.rotation.x)*.04;
    if(mode==='hero'){ root.position.x=Math.min(5.2,innerWidth/260)*(1-sy*1.2); root.position.y=-sy*5; cam.position.z=15+sy*6; }
    renderer.render(scene,cam); requestAnimationFrame(frame);
  }
  frame();
})();
/* tilt cards + reveal */
(function(){
  document.querySelectorAll('.tilt').forEach(function(c){
    c.addEventListener('pointermove',function(e){var b=c.getBoundingClientRect(),x=(e.clientX-b.left)/b.width-.5,y=(e.clientY-b.top)/b.height-.5;
      c.style.transform='perspective(900px) rotateY('+(x*14)+'deg) rotateX('+(-y*14)+'deg) translateZ(6px)';});
    c.addEventListener('pointerleave',function(){c.style.transform='';});
  });
  var io='IntersectionObserver' in window?new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},{threshold:.12}):null;
  document.querySelectorAll('.reveal').forEach(function(n){io?io.observe(n):n.classList.add('in');});
})();

addEventListener('pointermove',function(e){var r=document.documentElement.style;r.setProperty('--mx',e.clientX+'px');r.setProperty('--my',e.clientY+'px');});
