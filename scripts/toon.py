"""イラスト風の後処理: python toon.py in.png out.png [階調数]
色相を保ったまま明るさを階調に量子化し(セル塗り風)、ノイズを軽く均す。輪郭線はBlenderのFreestyleが描く。"""
import sys
import numpy as np
from PIL import Image, ImageFilter

src, dst = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 12
img = Image.open(src).convert("RGB").filter(ImageFilter.MedianFilter(3))
a = np.asarray(img).astype(np.float32) / 255
L = a.max(2, keepdims=True)
Lq = (np.floor(np.clip(L, 0, 1) * n) + 0.5) / n
Lq = np.where(L >= 0.97, L, Lq)  # 発光部は量子化せず、グローに回す
ratio = np.clip(Lq / (L + 1e-3), 0.4, 2.0)
out = np.clip(0.6 * a * ratio + 0.4 * a, 0, 1)
# 彩度をほんの少し上げる(イラストの色の乗り)
g = out.mean(2, keepdims=True)
out = np.clip(g + (out - g) * 1.12, 0, 1)
Image.fromarray((out * 255).astype(np.uint8)).save(dst)
