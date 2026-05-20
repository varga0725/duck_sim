import numpy as np
import cv2
import os

os.makedirs('external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/assets', exist_ok=True)

# Generate Wood Floor (Planks)
wood = np.zeros((512, 512, 3), dtype=np.uint8)
wood[:] = [100, 150, 200]  # Light brown in BGR (approx #C89664)
# Add some noise
noise = np.random.randint(-15, 15, (512, 512, 3), dtype=np.int16)
wood = np.clip(wood + noise, 0, 255).astype(np.uint8)
# Draw plank lines
for i in range(0, 512, 64):
    cv2.line(wood, (0, i), (512, i), (50, 100, 150), 2)
cv2.imwrite('external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/assets/wood.png', wood)

# Generate Brick Wall
brick = np.zeros((512, 512, 3), dtype=np.uint8)
brick[:] = [180, 180, 180]  # Mortar gray
for y in range(0, 512, 64):
    offset = 64 if (y // 64) % 2 == 0 else 0
    for x in range(-128 + offset, 512, 128):
        cv2.rectangle(brick, (x+4, y+4), (x+128-4, y+64-4), (40, 40, 180), -1)  # Red brick
cv2.imwrite('external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/assets/brick.png', brick)

# Generate ball pattern (soccer ball like)
ball = np.zeros((512, 512, 3), dtype=np.uint8)
ball[:] = [255, 255, 255]
for y in range(0, 512, 128):
    for x in range(0, 512, 128):
        if (x//128 + y//128) % 2 == 0:
            cv2.circle(ball, (x+64, y+64), 40, (0, 0, 0), -1)
cv2.imwrite('external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/assets/ball.png', ball)

print("Textures generated.")
