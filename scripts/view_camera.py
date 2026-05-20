#!/usr/bin/env python3
import time
import cv2
import requests
import numpy as np

API_URL = "http://127.0.0.1:8765"
FRAME_INTERVAL_SEC = 0.20  # 5 FPS: keep the Mac webcam/bridge responsive
STATUS_INTERVAL_SEC = 0.50
REQUEST_TIMEOUT_SEC = 2.0

def main():
    print("====================================================")
    # Highlight critical instructions using standard layout
    print("   Open Duck Mini v2 Live Vision Viewer")
    print("====================================================")
    print(f"Connecting to simulator bridge at: {API_URL}")
    print("Press 'q' in the window to quit.\n")

    # Check connection
    try:
        res = requests.get(f"{API_URL}/health")
        if res.status_code == 200:
            info = res.json()
            print(f"Connected successfully! Mode: {info.get('sim_mode', 'unknown')}")
        else:
            print(f"Error: API returned status code {res.status_code}")
            return
    except Exception as e:
        print(f"Could not connect to simulation bridge: {e}")
        print(f"Please make sure the bridge server is running (e.g. `./scripts/run_bridge.sh`).")
        return

    cv2.namedWindow("Open Duck Mini - Camera Stream", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Open Duck Mini - Camera Stream", 640, 480)
    session = requests.Session()
    latest_detections = []
    latest_follow_status = None
    last_status_fetch = 0.0

    while True:
        try:
            # 1. Fetch the raw JPEG camera frame
            frame_res = session.get(f"{API_URL}/vision/frame", timeout=REQUEST_TIMEOUT_SEC)
            if frame_res.status_code != 200:
                print(f"Failed to fetch frame: {frame_res.status_code}")
                time.sleep(0.1)
                continue
            
            # Decode JPEG to OpenCV image
            frame_bytes = np.frombuffer(frame_res.content, dtype=np.uint8)
            img = cv2.imdecode(frame_bytes, cv2.IMREAD_COLOR)
            
            if img is None:
                print("Failed to decode frame bytes.")
                time.sleep(0.1)
                continue

            # 2. Fetch the latest YOLO detections
            now = time.time()
            if now - last_status_fetch >= STATUS_INTERVAL_SEC:
                det_res = session.get(f"{API_URL}/vision/detections", timeout=REQUEST_TIMEOUT_SEC)
                if det_res.status_code == 200:
                    latest_detections = det_res.json().get("objects", [])

                fol_res = session.get(f"{API_URL}/vision/follow/status", timeout=REQUEST_TIMEOUT_SEC)
                if fol_res.status_code == 200:
                    latest_follow_status = fol_res.json()

                last_status_fetch = now

            # Draw latest detections on image
            for det in latest_detections:
                label = det["label"]
                conf = det["confidence"]
                x1, y1, x2, y2 = map(int, det["bbox"])
                track_id = det.get("tracking_id", -1)

                # Clamp boxes to the visible frame so full-frame detections do not
                # make the display look like it is resizing/zooming.
                h, w = img.shape[:2]
                x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
                y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))

                # Bounding Box color: vibrant cyan/teal
                color = (255, 255, 0) if label == "person" else (0, 255, 255)
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

                # Text label: label + ID + confidence
                txt = f"{label} ID:{track_id} ({conf:.2f})"
                cv2.putText(img, txt, (x1, max(15, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
            
            # 3. Draw Follower Status overlay if active
            if latest_follow_status is not None:
                status = latest_follow_status
                active = status["active"]
                state = status["state"]
                cmd_linear = status["commanded_linear_x"]
                cmd_yaw = status["commanded_yaw"]
                target_id = status["active_target_id"]

                # Draw top bar overlay
                overlay_color = (0, 165, 255) if active else (128, 128, 128)
                cv2.rectangle(img, (5, 5), (280, 85), (0, 0, 0), -1)
                cv2.rectangle(img, (5, 5), (280, 85), overlay_color, 1)

                cv2.putText(img, f"Follower: {'ACTIVE' if active else 'INACTIVE'}", (15, 22), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, overlay_color, 1, cv2.LINE_AA)
                cv2.putText(img, f"State: {state}", (15, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.putText(img, f"Cmd Speed: {cmd_linear:.2f} m/s", (15, 56), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.putText(img, f"Cmd Turn:  {cmd_yaw:.2f} rad/s", (15, 72), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)

            # Show window
            cv2.imshow("Open Duck Mini - Camera Stream", img)

        except Exception as e:
            print(f"Error in stream loop: {e}")
            time.sleep(0.5)

        # Break loop on 'q' key
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

        time.sleep(FRAME_INTERVAL_SEC)

    cv2.destroyAllWindows()
    print("Viewer closed.")

if __name__ == "__main__":
    main()
