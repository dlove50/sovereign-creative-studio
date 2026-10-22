"""Image Templates: one-click recipes over Sovereign's local image engines.

Each template declares the inputs the user fills in (pictures, text, choices) and a recipe that
turns them into ONE ordinary Sovereign generation:

  * engine "edit"     - local Qwen Image Edit 2509: a source picture plus up to two reference
                        pictures (more pictures are combined into a labelled reference sheet).
  * engine "generate" - local text-to-image (Flux / the default quality preset).
  * engine "enhance"  - the Universal AI Enhance pipeline (upscale / face restoration).

The catalogue mirrors the inputs and choices of a popular template gallery (see
docs/IMAGE_TEMPLATES_REFERENCE.md); the recipes and wording are Sovereign's own.
Results are normal generations, so they land in the library and history like any other image.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CATEGORIES = ["Trending", "Edit", "Product/Ads", "Photography", "Creative", "Tattoo"]
MAX_EDIT_IMAGES = 3  # Qwen Image Edit 2509 takes image1..image3


class TemplateError(ValueError):
    """A user-presentable reason a template cannot run."""


@dataclass(frozen=True)
class Field:
    id: str
    label: str
    kind: str  # image | images | text | select
    hint: str = ""
    placeholder: str = ""
    options: tuple[str, ...] = ()
    max_images: int = 1
    required: bool = True

    def public(self) -> dict[str, Any]:
        out = {"id": self.id, "label": self.label, "kind": self.kind, "hint": self.hint,
               "placeholder": self.placeholder, "required": self.required}
        if self.options:
            out["options"] = list(self.options)
        if self.kind == "images":
            out["max_images"] = self.max_images
        return out


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    categories: tuple[str, ...]
    engine: str  # edit | generate | enhance
    fields: tuple[Field, ...]
    recipe: Callable[[dict[str, Any]], str] = lambda v: ""
    # Order in which picture fields become image1, image2, image3 (edit engine).
    image_order: tuple[str, ...] = ()
    enhance_ops: tuple[dict[str, Any], ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "description": self.description,
                "categories": list(self.categories), "engine": self.engine,
                "fields": [f.public() for f in self.fields]}


def img(id_: str, label: str, hint: str = "") -> Field:
    return Field(id_, label, "image", hint)


def imgs(id_: str, label: str, max_images: int, hint: str = "") -> Field:
    return Field(id_, label, "images", hint, max_images=max_images)


def txt(id_: str, label: str, placeholder: str = "", hint: str = "") -> Field:
    return Field(id_, label, "text", hint, placeholder)


def sel(id_: str, label: str, options: tuple[str, ...], hint: str = "") -> Field:
    return Field(id_, label, "select", hint, options=options)


KEEP_ID = "Keep the person's face, identity, skin tone and expression exactly the same."
KEEP_PRODUCT = "Keep the product's exact shape, colours, materials, label and logo unchanged and legible."

TATTOO_STYLES = {
    "bw-tattoo": ("B-W Tattoo", "bold black-and-white tattoo with strong linework and solid black shading"),
    "colored-tattoo": ("Colored Tattoo", "vibrant full-colour tattoo with saturated inks and crisp outlines"),
    "creepy-tattoo": ("Creepy Tattoo", "dark, eerie tattoo with mysterious shadowy elements"),
    "geometric-tattoo": ("Geometric Tattoo", "geometric tattoo with clean precise lines, symmetry and structured patterns"),
    "portrait-tattoo": ("Portrait Tattoo", "realistic portrait tattoo with fine facial detail and soft black-and-grey shading"),
    "horror-tattoo": ("Horror Tattoo", "horror tattoo with unsettling, gory, dark details"),
    "8bit-tattoo": ("8-bit Tattoo", "8-bit pixel-art tattoo with crisp square pixels and a retro game palette"),
    "popart-tattoo": ("Pop-art Tattoo", "pop-art tattoo with bold flat colours, halftone dots and thick outlines"),
    "watercolor-tattoo": ("Watercolor Tattoo", "watercolour tattoo with fluid washes, soft bleeding colour and splashes"),
    "gothic-lettering-tattoo": ("Gothic Lettering Tattoo", "gothic blackletter lettering tattoo with dramatic calligraphic strokes"),
}


def _tattoo(style: str) -> Callable[[dict[str, Any]], str]:
    return lambda v: (f"Add a realistic {style} on the skin shown in image 1. The design: {v['details']}. "
                      "It must look like real healed ink on skin: follow the body's curvature, skin texture "
                      "and lighting. Do not change anything else in the photo.")


TEMPLATES: list[Template] = [
    # --- Trending / Creative ----------------------------------------------------------------
    Template("skyline-banner", "Skyline Banner", "A huge banner with your message, held up high above a city skyline.",
             ("Trending", "Creative"), "generate", (txt("text", "Banner text", "e.g. Made with Sovereign"),),
             lambda v: (f'Dramatic photo of a person standing on a skyscraper rooftop edge at golden hour holding up a '
                        f'giant white cloth banner with the hand-painted words "{v["text"]}" in large black letters, '
                        "city skyline far below, wind in the banner, cinematic wide shot, photorealistic, sharp text")),
    Template("disco-ball-logo", "Disco Ball Logo", "Your logo rebuilt as a glittering mirror-ball icon.",
             ("Trending", "Creative"), "edit", (img("logo", "Logo", "Upload your logo"),),
             lambda v: ("Rebuild the logo in image 1 as a glossy 3D disco mirror-ball icon: the same silhouette and shape, "
                        "covered in tiny reflective mirror tiles with sparkling highlights, rounded app-icon square on a "
                        "dark gradient background, studio lighting, crisp edges"), ("logo",)),
    Template("family-toon", "Family Toon", "Your family photo as a playful animated-film cartoon portrait.",
             ("Trending", "Creative"), "edit",
             (img("photo", "Family photo"), txt("background", "Background colour", "e.g. pastel yellow")),
             lambda v: ("Redraw everyone in image 1 as characters from a modern 3D animated family film: big expressive "
                        "eyes, soft rounded features, each person still clearly recognisable with the same hair, clothes "
                        f"and poses, cheerful group portrait on a plain {v['background']} background"), ("photo",)),
    Template("crayon-doodle", "Crayon Doodle", "Turn a social profile or photo into hand-drawn crayon doodle art.",
             ("Trending", "Creative"), "edit", (img("photo", "Profile screenshot or photo"),),
             lambda v: ("Redraw image 1 as a playful hand-drawn crayon doodle on white paper: wobbly colourful crayon "
                        "strokes, childlike charm, keep the layout, people and main elements recognisable"), ("photo",)),
    Template("character-swap", "Character Swap", "Replace one character in a scene and keep everything else.",
             ("Trending", "Edit"), "edit",
             (img("scene", "Scene image", "The picture with the character to replace"),
              img("character", "New character", "Who should take their place")),
             lambda v: ("Replace the main character in image 1 with the character from image 2. Keep the scene, pose, "
                        "framing, lighting, camera angle and every other detail of image 1 unchanged; the new character "
                        "keeps the face, hair and outfit from image 2 and matches the scene's lighting"),
             ("scene", "character")),
    Template("product-ads-styles", "Product Ads in Different Styles", "Your product as a polished advertisement.",
             ("Trending", "Product/Ads"), "edit", (img("product", "Product image"),),
             lambda v: ("Create a premium advertising image of the product in image 1: bold art-directed composition, "
                        f"dramatic studio lighting, complementary colour backdrop with props, magazine-ad quality. {KEEP_PRODUCT}"),
             ("product",)),
    Template("comic-book", "Comic Book", "A comic-book panel starring two of your characters.",
             ("Trending", "Creative"), "edit",
             (img("main", "Main character"), img("second", "Second character"),
              sel("genre", "Genre", ("Action", "Romantic", "High Fantasy", "Horror", "Sci-fi", "Comedy", "Teen Drama")),
              sel("style", "Style", ("Golden age", "Noir", "Ligne Claire", "Manga"))),
             lambda v: (f"A {v['genre'].lower()} comic book page in {v['style']} comic art style starring the person from "
                        "image 1 as the hero and the person from image 2 as the second character, three dynamic panels "
                        "with speech bubbles and inked outlines, both people recognisable"), ("main", "second")),
    Template("sticker-maker", "Sticker Maker", "Any photo as a die-cut sticker with a clean white border.",
             ("Trending", "Creative"), "edit",
             (img("photo", "Photo"), sel("style", "Style", ("Anime", "Manga", "Cyberpunk", "Realistic"))),
             lambda v: (f"Turn the subject of image 1 into a {v['style'].lower()}-style die-cut sticker: bold clean "
                        "outline, thick white sticker border, slight glossy shine, centred on a plain light background, "
                        "subject recognisable"), ("photo",)),
    Template("different-angles", "Different Angles", "See your photo from new camera angles.",
             ("Trending", "Edit", "Photography"), "edit", (img("photo", "Image"),),
             lambda v: ("Show the same subject and scene as image 1 from a clearly different camera angle (three-quarter "
                        "view from a higher viewpoint). Keep identity, clothing, materials and lighting consistent"),
             ("photo",)),
    Template("outfit-try-on", "Outfit Try-On", "Put up to three outfits on your photo.",
             ("Trending", "Edit", "Photography"), "edit",
             (img("photo", "Your photo"), imgs("outfits", "Outfits", 3, "Up to 3 clothing pictures")),
             lambda v: ("Dress the person in image 1 in the clothing shown in the other image(s), fitted naturally to "
                        f"their body and pose, realistic fabric folds and lighting. {KEEP_ID}"), ("photo", "outfits")),
    Template("movie-poster", "Movie Poster Creator", "Star in your own cinematic movie poster.",
             ("Trending", "Creative"), "edit",
             (img("photo", "Your portrait"),
              sel("genre", "Genre", ("Action", "Romance", "Super Hero", "Horror", "Science Fiction", "Crime",
                                     "Historical Epic", "Western", "Comedy"))),
             lambda v: (f"A cinematic {v['genre'].lower()} movie poster starring the person from image 1 as the lead "
                        "character, genre-appropriate costume and dramatic key art, title area at the top and credits "
                        f"block at the bottom, theatrical one-sheet layout. {KEEP_ID}"), ("photo",)),
    # --- Edit -----------------------------------------------------------------------------------
    Template("restore-old-photos", "Restore Old Photos", "Repair scratches, fading and damage in old photos.",
             ("Edit", "Photography"), "edit", (img("photo", "Old photo"),),
             lambda v: ("Restore this old photograph: remove scratches, dust, creases, stains and tears, recover faded "
                        "contrast and natural tones, sharpen softly. Keep every face, pose and detail exactly the same; "
                        "do not add or remove anything"), ("photo",)),
    Template("drone-shot", "Drone Shot", "Your scene seen from a cinematic aerial drone view.",
             ("Edit", "Photography"), "edit", (img("photo", "Image"),),
             lambda v: ("Show the scene of image 1 from a high cinematic drone shot looking down at an angle, same place, "
                        "subjects and lighting, wide aerial perspective"), ("photo",)),
    Template("translate-text", "Translate Text in Design", "Translate the text in a design and keep the layout.",
             ("Edit",), "edit", (img("design", "Design image"), txt("language", "Target language", "e.g. Spanish")),
             lambda v: (f"Translate every piece of visible text in image 1 into {v['language']}. Keep the exact layout, "
                        "fonts, sizes, colours, alignment and all graphics unchanged; only the words change"), ("design",)),
    Template("illustration-studio", "Illustration Studio", "Your photo as an illustration in the style you pick.",
             ("Edit", "Creative"), "edit",
             (img("photo", "Image"),
              sel("style", "Illustration style", ("Caricature", "Comic Book", "Editorial", "Watercolor",
                                                   "Digital Painting", "Sketch", "Flat Vector"))),
             lambda v: (f"Redraw image 1 as a {v['style'].lower()} illustration, keeping the composition and the "
                        "subject recognisable"), ("photo",)),
    Template("product-scene", "Product Scene", "Place your product in a real-life setting you describe.",
             ("Edit", "Product/Ads"), "edit",
             (img("product", "Product image"), txt("scene", "Scene description", "e.g. on a kitchen counter at sunrise")),
             lambda v: (f"Place the product from image 1 naturally into this scene: {v['scene']}. Correct scale, contact "
                        f"shadows and matching light, lifestyle photography. {KEEP_PRODUCT}"), ("product",)),
    Template("skin-enhancer", "Skin Enhancer", "Natural skin detail with the face kept identical.",
             ("Edit",), "enhance", (img("photo", "Portrait"),),
             enhance_ops=({"op": "face_restore", "params": {"fidelity": 0.85}},)),
    Template("image-enhancer", "Image Enhancer", "Clearer, sharper, higher-resolution images.",
             ("Edit",), "enhance", (img("photo", "Image"),),
             enhance_ops=({"op": "denoise", "params": {"strength": 0.3}}, {"op": "upscale_ai", "params": {"scale": 2}})),
    Template("recolor", "Recolor", "Recolour one part of an image, keeping texture and light.",
             ("Edit", "Photography"), "edit",
             (img("photo", "Image"), txt("region", "Region to recolour", "e.g. t-shirt, car body, wall"),
              txt("color", "New colour", "e.g. matte black, pastel blue")),
             lambda v: (f"Change only the colour of the {v['region']} in image 1 to {v['color']}. Keep its texture, "
                        "shading, reflections and everything else in the image exactly the same"), ("photo",)),
    # --- Product / Ads --------------------------------------------------------------------------
    Template("product-composition", "Product Composition Builder", "Combine up to six products into one hero shot.",
             ("Product/Ads", "Photography"), "edit", (imgs("products", "Products", 6, "Up to 6 product pictures"),),
             lambda v: ("Arrange all the products shown in the images into one premium, balanced hero composition on an "
                        f"elegant studio set with soft shadows. {KEEP_PRODUCT}"), ("products",)),
    Template("alternative-logos", "Alternative Logos", "Fresh variations of your existing logo.",
             ("Product/Ads",), "edit", (img("logo", "Original logo", "High-resolution logos give sharper results"),),
             lambda v: ("Design four alternative variations of the logo in image 1 in a 2x2 grid on white: keep the brand "
                        "name and core idea, explore different marks, weights and layouts, flat vector, crisp"), ("logo",)),
    Template("product-campaign", "Product to Campaign Visual", "A campaign-style key visual for your product.",
             ("Product/Ads",), "edit",
             (img("product", "Product image"), txt("context", "Campaign context", "e.g. minimal marble bathroom, morning light")),
             lambda v: (f"A premium advertising campaign key visual of the product from image 1 in: {v['context']}. "
                        f"Art-directed lighting and styling, high-end commercial photography. {KEEP_PRODUCT}"), ("product",)),
    Template("product-photoshoot", "Product Photoshoot", "A clean professional studio shoot of your products.",
             ("Product/Ads", "Photography"), "edit",
             (imgs("products", "Products", 6, "Up to 6 product pictures"),
              sel("style", "Photoshoot style", ("Studio Minimal", "Luxury Premium", "Bold Color Pop", "Dark Dramatic"))),
             lambda v: (f"A professional {v['style'].lower()} studio product photoshoot of the products shown, "
                        f"perfect lighting and reflections, catalogue quality. {KEEP_PRODUCT}"), ("products",)),
    Template("video-thumbnail", "Video Thumbnail Generator", "A click-worthy video thumbnail with you and a product.",
             ("Product/Ads",), "edit",
             (img("person", "Person"), img("product", "Product"),
              txt("topic", "Video description", "e.g. I tested every phone camera for 30 days"),
              sel("style", "Thumbnail style", ("Shock Reaction", "Premium Review", "Minimal Lifestyle", "Comparison",
                                               "Future Tech", "Educational Guide", "Travel Adventure"))),
             lambda v: (f"A 16:9 YouTube thumbnail in a {v['style'].lower()} style for a video about: {v['topic']}. The "
                        "person from image 1 large on one side with a strong expressive reaction, the product from image 2 "
                        "prominent, high contrast, bold short headline text, clean background"), ("person", "product")),
    Template("giant-product-ad", "Giant Product Ad", "Your product as a monumental, larger-than-life visual.",
             ("Product/Ads",), "edit",
             (img("product", "Product image", "Use a clear product photo"),
              sel("environment", "Environment", ("Luxury", "Tech/Futuristic", "Eco", "Sport"))),
             lambda v: (f"The product from image 1 as a giant monumental object towering over a {v['environment'].lower()} "
                        f"landscape, tiny people for scale, epic campaign visual. {KEEP_PRODUCT}"), ("product",)),
    Template("macro-close-up", "Macro Close-Up", "An ultra-detailed macro photograph of your subject.",
             ("Product/Ads", "Photography"), "edit", (img("subject", "Subject"),),
             lambda v: ("An extreme macro photograph of the subject in image 1: razor-thin depth of field, micro texture "
                        "detail, soft bokeh background, professional macro lens look"), ("subject",)),
    Template("ghost-mannequin", "Ghost Mannequin", "E-commerce invisible-mannequin clothing shots.",
             ("Product/Ads",), "edit",
             (img("clothing", "Clothing image", "On a model or flat lay"), txt("background", "Background colour", "e.g. white")),
             lambda v: ("Show only the garment from image 1 as an e-commerce ghost-mannequin shot: the clothing keeps its "
                        f"3D worn shape with the person removed, hollow neck opening, plain {v['background']} background, "
                        "even studio light, exact fabric, colour and print"), ("clothing",)),
    Template("shadow-maker", "Shadow Maker", "Natural, realistic shadows for clean product shots.",
             ("Product/Ads",), "edit", (img("product", "Product image"),),
             lambda v: (f"Place the product from image 1 on a clean seamless surface and add a realistic soft contact "
                        f"shadow and natural cast shadow from a single soft light. {KEEP_PRODUCT}"), ("product",)),
    Template("tshirt-mockup", "T-Shirt Mockup", "Your design printed on a realistic garment.",
             ("Product/Ads",), "edit",
             (img("design", "Design image"), txt("color", "Garment colour", "e.g. navy blue"),
              sel("placement", "Print placement", ("Front Center", "Back", "Chest Area")),
              sel("model", "Model", ("Women", "Man", "No Model")),
              sel("shot", "Shot type", ("A close-up of the printed area", "A mid-shot including torso and head"))),
             lambda v: (f"A realistic {v['color']} t-shirt mockup with the design from image 1 printed at the "
                        f"{v['placement'].lower()}, "
                        + ("laid flat, no model" if v["model"] == "No Model" else f"worn by a {'woman' if v['model'] == 'Women' else 'man'}")
                        + f"; {v['shot'].lower()}; the print follows fabric folds, exact design and colours"), ("design",)),
    # --- Photography ----------------------------------------------------------------------------
    Template("hair-style", "Hair Style Changer", "Try a new hairstyle from a reference picture.",
             ("Photography",), "edit", (img("photo", "Your photo"), img("reference", "Reference hairstyle")),
             lambda v: (f"Give the person in image 1 the hairstyle shown in image 2 (cut, length and styling). {KEEP_ID}"),
             ("photo", "reference")),
    Template("hair-color", "Hair Color Changer", "Try a new hair colour from a reference picture.",
             ("Photography",), "edit", (img("photo", "Your photo"), img("reference", "Reference hair colour")),
             lambda v: (f"Change only the hair colour of the person in image 1 to the hair colour in image 2, keeping "
                        f"their haircut. {KEEP_ID}"), ("photo", "reference")),
    Template("linkedin-photo", "LinkedIn Photo Pack", "A polished professional headshot from your photos.",
             ("Photography",), "edit", (imgs("photos", "Your photos", 3, "1-3 photos for better likeness"),),
             lambda v: ("A professional corporate headshot of this person: business attire, soft studio lighting, neutral "
                        f"grey background, shoulders up, friendly confident expression. {KEEP_ID}"), ("photos",)),
    Template("behind-the-scenes", "Behind the Scenes", "The film set behind the final shot.",
             ("Photography",), "edit", (img("photo", "Photo"),),
             lambda v: ("A wider behind-the-scenes photo of the shoot that produced image 1: the same subject and set "
                        "visible in the middle, with crew, cameras, lights, stands and cables around it"), ("photo",)),
    # --- Creative -------------------------------------------------------------------------------
    Template("coloring-page", "Coloring Page Creator", "Turn any image into a printable colouring page.",
             ("Creative",), "edit",
             (img("photo", "Image"), sel("detail", "Detail level", ("Low", "Medium", "High"))),
             lambda v: (f"Convert image 1 into a black-and-white colouring-book page with {v['detail'].lower()} detail: "
                        "clean closed outlines, no shading, no fill, white background"), ("photo",)),
    Template("sketch-to-reality", "Turn Sketch Into Reality", "Your sketch as a realistic, lifelike scene.",
             ("Creative",), "edit", (img("sketch", "Sketch"),),
             lambda v: ("Turn the sketch in image 1 into a photorealistic scene with real materials, lighting and depth, "
                        "keeping the composition and every element of the drawing"), ("sketch",)),
    Template("tattoo-designer", "Tattoo Designer", "A unique tattoo design from your idea.",
             ("Creative", "Tattoo"), "generate",
             (txt("idea", "Tattoo idea", "e.g. phoenix, lion with crown"),
              sel("style", "Tattoo style", ("Minimalist", "Japanese", "Realism", "Fineline", "Geometric", "Watercolor")),
              sel("creativity", "Creativity", ("Basic", "Styled", "Creative", "Artistic"))),
             lambda v: (f"Tattoo flash design of {v['idea']}, {v['style'].lower()} tattoo style, "
                        + {"Basic": "simple and literal", "Styled": "well stylised", "Creative": "inventive composition",
                           "Artistic": "highly artistic and unexpected"}[v["creativity"]]
                        + ", clean linework on plain white paper, centred, no skin")),
    Template("interior-designer", "Interior Designer", "Redesign your room in a new style.",
             ("Creative",), "edit",
             (img("room", "Your room", "A clear photo of the space"),
              sel("room_type", "Room type", ("Living Room", "Bedroom", "Dining Room", "Home Office / Study", "Bathroom",
                                             "Kitchen", "Kids Room", "Nursery", "Man Cave", "Game Room", "Home Gym",
                                             "Home Theater")),
              sel("style", "Style", ("Minimalist", "Scandinavian", "Japandi", "Industrial", "Luxury Contemporary")),
              sel("creativity", "Creativity", ("Subtle", "Styled (Recommended)", "Creative"))),
             lambda v: (f"Redesign the room in image 1 as a {v['style'].lower()} {v['room_type'].lower()}. "
                        + {"Subtle": "Keep the layout, windows and most furniture positions; refresh finishes and decor.",
                           "Styled (Recommended)": "Keep walls, windows and layout; replace furniture and decor.",
                           "Creative": "Keep the walls and windows; reimagine everything else boldly."}[v["creativity"]]
                        + " Photorealistic interior photography"), ("room",)),
    Template("spirit-animal", "Spirit Animal", "Your animal alter ego.",
             ("Creative",), "edit", (img("photo", "Your photo"), sel("animal", "Animal", ("Cat", "Dog", "Animal"))),
             lambda v: ("Transform the person in image 1 into an anthropomorphic "
                        + ("animal that best matches their personality" if v["animal"] == "Animal" else v["animal"].lower())
                        + " character with the same outfit, pose, hairstyle colours and expression, charming portrait"),
             ("photo",)),
] + [
    Template(tid, name, f"Preview a {name.lower().replace(' tattoo', '')} tattoo on your own skin.", ("Tattoo",), "edit",
             (img("photo", "Body area photo", "Where you are thinking of getting it"),
              txt("details", "Tattoo details", "e.g. a small butterfly")),
             _tattoo(style), ("photo",))
    for tid, (name, style) in TATTOO_STYLES.items()
]

BY_ID = {t.id: t for t in TEMPLATES}


def catalog() -> dict[str, Any]:
    return {"categories": CATEGORIES, "templates": [t.public() for t in TEMPLATES]}


def get(template_id: str) -> Template:
    t = BY_ID.get(template_id)
    if not t:
        raise TemplateError("Unknown template.")
    return t


def validate(t: Template, values: dict[str, Any], images: dict[str, list[Path]]) -> dict[str, Any]:
    """Check every required field; returns clean text/select values."""
    clean: dict[str, Any] = {}
    for f in t.fields:
        if f.kind in ("image", "images"):
            got = images.get(f.id, [])
            if f.required and not got:
                raise TemplateError(f"{f.label}: add a picture.")
            if len(got) > f.max_images:
                raise TemplateError(f"{f.label}: at most {f.max_images} pictures.")
        else:
            value = str(values.get(f.id, "")).strip()
            if f.required and not value:
                raise TemplateError(f"{f.label} is required.")
            if f.kind == "select" and value not in f.options:
                raise TemplateError(f"{f.label}: choose one of the options.")
            if len(value) > 400:
                raise TemplateError(f"{f.label} is too long.")
            clean[f.id] = value
    return clean


def contact_sheet(paths: list[Path], out: Path, cell: int = 640) -> Path:
    """Several pictures as one labelled reference sheet (used when a template has more than 3 images)."""
    from PIL import Image, ImageOps

    cols = 2 if len(paths) <= 4 else 3
    rows = -(-len(paths) // cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), "white")
    for i, p in enumerate(paths):
        with Image.open(p) as raw:
            pic = ImageOps.contain(ImageOps.exif_transpose(raw).convert("RGB"), (cell - 24, cell - 24))
        x, y = (i % cols) * cell, (i // cols) * cell
        sheet.paste(pic, (x + (cell - pic.width) // 2, y + (cell - pic.height) // 2))
    sheet.save(out, "PNG")
    return out


def edit_images(t: Template, images: dict[str, list[Path]], workdir: Path) -> list[Path]:
    """image1..image3 for the edit engine, in the template's order; extra pictures share one sheet."""
    ordered: list[Path] = []
    for key in t.image_order:
        ordered.extend(images.get(key, []))
    if len(ordered) <= MAX_EDIT_IMAGES:
        return ordered
    head, rest = ordered[:MAX_EDIT_IMAGES - 1], ordered[MAX_EDIT_IMAGES - 1:]
    return head + [contact_sheet(rest, workdir / "reference-sheet.png")]


def build_prompt(t: Template, values: dict[str, Any]) -> str:
    return " ".join(t.recipe(values).split())
