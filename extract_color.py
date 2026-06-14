from PIL import Image
from collections import Counter

img = Image.open('/Users/swj/Pictures/Photos Library.photoslibrary/resources/derivatives/masters/E/EB856C98-976A-40E5-AC78-22A6535A36BA_4_5005_c.jpeg')
pixels = list(img.getdata())
# Extract background (most common color)
bg_color = Counter(pixels).most_common(1)[0][0]
print(f"Background (Navy): #{bg_color[0]:02x}{bg_color[1]:02x}{bg_color[2]:02x}")

# Find the gold color by looking for pixels with high red/green and lower blue
golds = [p for p in pixels if p[0] > 150 and p[1] > 120 and p[2] < 100]
if golds:
    gold_color = Counter(golds).most_common(1)[0][0]
    print(f"Text/Badge (Gold): #{gold_color[0]:02x}{gold_color[1]:02x}{gold_color[2]:02x}")
