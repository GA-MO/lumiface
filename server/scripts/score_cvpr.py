import glob, sys, cv2, numpy as np, onnxruntime as ort
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.services.face import decode_image, get_face_engine
MEAN=np.array([0.485,0.456,0.406],np.float32); STD=np.array([0.229,0.224,0.225],np.float32)
def prep(bgr):
    rgb=cv2.cvtColor(cv2.resize(bgr,(224,224)),cv2.COLOR_BGR2RGB).astype(np.float32)/255
    return ((rgb-MEAN)/STD).transpose(2,0,1)[None]
def face_crop(img, bbox, margin=0.2):
    x1,y1,x2,y2=bbox; w,h=x2-x1,y2-y1; H,W=img.shape[:2]
    x1=max(0,int(x1-w*margin)); y1=max(0,int(y1-h*margin)); x2=min(W,int(x2+w*margin)); y2=min(H,int(y2+h*margin))
    return img[y1:y2,x1:x2]
names=sys.argv[1:]
sess={n: ort.InferenceSession(f"weights/cvpr2024/{n}.onnx", providers=["CPUExecutionProvider"]) for n in names}
eng=get_face_engine()
for grp in ("real","replay_phone"):
    print("==",grp)
    for f in sorted(glob.glob(f"data/samples/{grp}/*.jpg")):
        img=decode_image(open(f,'rb').read()); faces=eng.analyze(img)
        crop=face_crop(img, faces[0].bbox) if faces else img
        out=[]
        for n,s in sess.items():
            live_full=float(s.run(None,{"input":prep(img)})[0][0][0]); live_face=float(s.run(None,{"input":prep(crop)})[0][0][0])
            out.append(f"{n[:8]} full={live_full:.3f} face={live_face:.3f}")
        print(f"  {f.split('/')[-1]:34}", " | ".join(out))
