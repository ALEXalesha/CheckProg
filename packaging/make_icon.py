import os

from PIL import Image, ImageDraw

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "checkprog", "icon.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.06
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=size * 0.2,
                        fill=(46, 125, 50, 255))
    points = [(size * 0.27, size * 0.53), (size * 0.44, size * 0.70), (size * 0.75, size * 0.34)]
    d.line(points, fill=(255, 255, 255, 255), width=max(2, round(size * 0.11)), joint="curve")
    return img


def main():
    frames = [draw(s) for s in SIZES]
    frames[-1].save(os.path.abspath(TARGET), format="ICO",
                    sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print(os.path.abspath(TARGET))


if __name__ == "__main__":
    main()
