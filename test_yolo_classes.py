import cv2
from ultralytics import YOLO

# Load the saved frame
frame = cv2.imread("fpv_test_frame.png")
# YOLO expects RGB
frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

print("Loading yolov8n.pt...")
model = YOLO("yolov8n.pt")

print("Running inference with conf=0.01...")
results = model(frame_rgb, conf=0.01, verbose=True)

if results:
    result = results[0]
    boxes = result.boxes
    print(f"\nFound {len(boxes)} candidate boxes above 0.01 confidence:")
    for i, box in enumerate(boxes):
        cls_id = int(box.cls[0])
        label = result.names[cls_id]
        conf = float(box.conf[0])
        xyxy = box.xyxy[0].tolist()
        print(f"[{i}] Label: {label}, Confidence: {conf:.4f}, BBox: {xyxy}")
else:
    print("No results at all.")
