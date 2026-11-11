Add approved family photographs below this folder, then add a matching entry to manifest.json.
Use original images or images you have permission to display; avoid identifiable photos of
other families' babies without consent. 16:9 landscape photos work best on the projector.

The manifest is a JSON list. Each entry has an id, image path and caption; category and
author are optional. Example:

[
  {
    "id": "motherhood-001",
    "image": "/static/photos/motherhood/photo1.jpg",
    "caption": "A tiny hand can hold an entire heart.",
    "category": "Love"
  }
]

Keep the image path under /static/photos/. The app ignores missing, unsupported or unsafe
paths and shows a placeholder when no valid slides are available. Private photos are
excluded from Git by default; upload them directly to the host instead of committing them.

Included artwork credits:
- "Mother child (1934) vintage illustration", artwork by Mikuláš Galanda, via Rawpixel,
  CC0 1.0: https://www.rawpixel.com/image/9758974/image-people-art-vintage
- "Young Mother Sewing" (1900), artwork by Mary Cassatt; image photograph by Gandalf's
  Gallery, CC BY-SA 2.0:
  https://www.flickr.com/photos/45482849@N03/4967509024
  https://creativecommons.org/licenses/by-sa/2.0/
