import sys
import io
from PIL import Image

# Add path to cloned Nougat repo
sys.path.append(r"D:\Projects\nougat")

from nougat.inference import NougatModel
from nougat.utils.dataset import NougatDataset

# Load the model globally (only once)
model = NougatModel.from_pretrained("nougat-base")
model.eval()

def nougat_parse_page(image_bytes):
    """Parse a single PDF page image into structured text using Nougat."""
    img = Image.open(io.BytesIO(image_bytes))
    sample = {"image": img, "name": "page.png"}
    result = model.inference([sample])
    return result[0]


def page_is_math_heavy(text):
    math_symbols = ['=', '+', '-', '/', '\\', '∑', '∫', '^', '_', '{', '}']
    return sum(text.count(sym) for sym in math_symbols) > 10 or len(text.strip()) < 50
