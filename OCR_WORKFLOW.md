# OCR Workflow for Form Processing

## Overview

This document describes the workflow for processing scanned physical forms using OCR (Optical Character Recognition) to automatically extract form structure and data into JSON format.

## Workflow Steps

### 1. Form Scanning

- **Input**: Physical paper form
- **Process**: Scan using scanner or mobile camera
- **Output**: Image file (PDF, PNG, JPG)
- **Recommended settings**:
  - DPI: 300 or higher
  - Color mode: Grayscale or Color
  - Format: PDF for multi-page, PNG for single page

### 2. Image Preprocessing

Clean up the scanned image for better OCR accuracy:

```python
preprocessing_steps = [
    "deskew",               # Correct rotation/skew
    "denoise",              # Remove noise/artifacts
    "binarization",         # Convert to black & white
    "contrast_enhancement"  # Improve text clarity
]
```

### 3. OCR Extraction

Extract text and layout information:

**OCR Engines Supported:**

- Google Vision API (recommended for Vietnamese)
- Azure Computer Vision
- Tesseract OCR
- AWS Textract

**Example using Google Vision API:**

```python
from google.cloud import vision

def ocr_form(image_path):
    client = vision.ImageAnnotatorClient()

    with open(image_path, 'rb') as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.document_text_detection(image=image)

    # Extract text blocks with bounding boxes
    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            # Process each text block
            confidence = block.confidence
            vertices = [(v.x, v.y) for v in block.bounding_box.vertices]
            text = ''.join([symbol.text for paragraph in block.paragraphs
                           for word in paragraph.words
                           for symbol in word.symbols])
```

### 4. Form Structure Detection

Identify form components:

**Components to detect:**

- Header (organization name, logo, address)
- Title
- Field labels and input areas
- Signature lines
- Footer notes

**Detection methods:**

1. **Text pattern matching**: Detect labels using regex patterns
2. **Layout analysis**: Identify input areas by whitespace/boxes
3. **Line detection**: Find underlines and boxes indicating input fields
4. **Template matching**: Match against known form templates

### 5. Field Mapping

Map detected text to form fields:

```json
{
  "field_regions": [
    {
      "field_name": "full_name",
      "bbox": {"x": 245, "y": 380, "width": 520, "height": 45},
      "confidence": 0.96
    }
  ]
}
```

### 6. JSON Generation

Generate form definition JSON:

**Structure includes:**

1. **Form metadata**: ID, title, aliases
2. **Style information**: Layout, colors, fonts, spacing
3. **OCR metadata**: Source file, confidence, dimensions
4. **Fields**: Name, label, type, validators
5. **Field OCR data**: Extracted text, confidence, bbox, alternatives

**Example output:**

```json
{
  "form_id": "don_nhan_luong_huu",
  "title": "Đơn đề nghị nhận lương hưu qua tài khoản",
  "style": {
    "header": {
      "organization": "BẢO HIỂM XÃ HỘI VIỆT NAM",
      "align": "center"
    },
    "layout": {
      "type": "two-column",
      "label_position": "left"
    }
  },
  "ocr_metadata": {
    "source_file": "don_luong_huu_scan_001.pdf",
    "ocr_engine": "Google Vision API",
    "confidence_score": 0.94
  },
  "fields": [
    {
      "name": "full_name",
      "label": "Họ và tên",
      "ocr_data": {
        "extracted_text": "NGUYỄN VĂN THÀNH",
        "confidence": 0.96,
        "requires_review": false
      }
    }
  ]
}
```

### 7. Quality Assurance

Review and validate OCR results:

**Automated checks:**

- Confidence score thresholds
- Field validation rules
- Pattern matching for known field types

**Manual review triggers:**

- `confidence < 0.85`: Flag for review
- `requires_review: true`: Fields with ambiguous OCR
- Validation failures: Fields that don't match expected patterns

### 8. Human Review Interface

For low-confidence fields:

```text
Field: Số CCCD/CMND
OCR Result: 079058001234 (confidence: 0.89)
Alternatives:
  1. 079058OO1234 (0.65)
  2. 079O58001234 (0.58)

⚠️ Requires Review
[Show Original Image] [Accept] [Edit] [Select Alternative]
```

## Implementation Example

### Complete OCR Pipeline

```python
#!/usr/bin/env python3
"""OCR Form Processing Pipeline"""

import json
from pathlib import Path
from google.cloud import vision
from PIL import Image
import cv2
import numpy as np

class FormOCRProcessor:
    def __init__(self, ocr_engine="google_vision"):
        self.ocr_engine = ocr_engine
        self.client = vision.ImageAnnotatorClient()

    def preprocess_image(self, image_path):
        """Preprocess scanned image"""
        img = cv2.imread(str(image_path))

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray)

        # Deskew (simple rotation correction)
        # ... deskew logic here

        # Enhance contrast
        enhanced = cv2.equalizeHist(denoised)

        return enhanced

    def extract_text_blocks(self, image_path):
        """Extract text with bounding boxes using OCR"""
        with open(image_path, 'rb') as f:
            content = f.read()

        image = vision.Image(content=content)
        response = self.client.document_text_detection(image=image)

        blocks = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                text = self._get_block_text(block)
                bbox = self._get_bbox(block.bounding_box)

                blocks.append({
                    'text': text,
                    'bbox': bbox,
                    'confidence': block.confidence
                })

        return blocks

    def detect_form_structure(self, blocks):
        """Detect form header, title, fields, footer"""
        # Analyze text blocks to identify structure
        header = self._detect_header(blocks)
        title = self._detect_title(blocks)
        fields = self._detect_fields(blocks)
        footer = self._detect_footer(blocks)

        return {
            'header': header,
            'title': title,
            'fields': fields,
            'footer': footer
        }

    def generate_form_json(self, structure, metadata):
        """Generate form definition JSON"""
        form_json = {
            'form_id': self._generate_form_id(structure['title']),
            'title': structure['title'],
            'style': self._extract_style(structure),
            'ocr_metadata': metadata,
            'fields': structure['fields']
        }

        return form_json

    def process_form(self, image_path, output_path):
        """Complete OCR processing pipeline"""
        # Step 1: Preprocess
        processed_img = self.preprocess_image(image_path)

        # Step 2: Extract text blocks
        blocks = self.extract_text_blocks(image_path)

        # Step 3: Detect structure
        structure = self.detect_form_structure(blocks)

        # Step 4: Generate metadata
        metadata = {
            'source_file': Path(image_path).name,
            'ocr_engine': self.ocr_engine,
            'confidence_score': self._calc_avg_confidence(blocks)
        }

        # Step 5: Generate JSON
        form_json = self.generate_form_json(structure, metadata)

        # Step 6: Save output
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(form_json, f, ensure_ascii=False, indent=2)

        return form_json

# Usage
if __name__ == '__main__':
    processor = FormOCRProcessor()
    result = processor.process_form(
        'scans/don_luong_huu.pdf',
        'forms/don_luong_huu_ocr.json'
    )
    print(f"Form processed: {result['form_id']}")
```

## Best Practices

### 1. Scanning Quality

- Use **300 DPI** minimum for text documents
- Ensure good **lighting** (no shadows)
- Keep form **flat** (no wrinkles/folds)
- Use **color/grayscale** to preserve form structure

### 2. OCR Accuracy

- **Vietnamese language**: Use Google Vision API or Azure (better Unicode support)
- **Numbers**: Verify with regex patterns (CCCD, phone numbers)
- **Dates**: Parse with strict format validation
- **Handwriting**: Use specialized models (lower accuracy, requires review)

### 3. Confidence Thresholds

```python
CONFIDENCE_LEVELS = {
    'high': 0.95,      # Auto-accept
    'medium': 0.85,    # Flag for quick review
    'low': 0.70,       # Manual verification required
    'reject': 0.70     # Below this: reject OCR result
}
```

### 4. Error Handling

- **Common OCR errors**: O/0, l/I/1, S/5, B/8
- **Validation**: Apply field validators to catch errors
- **Alternatives**: Keep top 3 OCR alternatives for review

### 5. Style Extraction

```python
# Extract layout from detected elements
layout_type = detect_layout(blocks)  # single-column, two-column, grid

# Detect colors from original image
colors = extract_dominant_colors(image)

# Measure spacing
spacing = calculate_field_spacing(field_bboxes)
```

## Form Schema Validation

After generating JSON, validate against schema:

```bash
# Using jsonschema
pip install jsonschema

python -c "
import json
import jsonschema

with open('schemas/form_schema.json') as f:
    schema = json.load(f)

with open('forms/generated_form.json') as f:
    form = json.load(f)

jsonschema.validate(form, schema)
print('✓ Form JSON is valid')
"
```

## Integration with Application

### Loading OCR-generated forms

```python
# In app.py
def load_ocr_forms():
    """Load forms with OCR metadata"""
    forms = []

    for form_file in Path('forms').glob('*_ocr.json'):
        with open(form_file) as f:
            form = json.load(f)

        # Check if OCR review needed
        if form.get('ocr_metadata', {}).get('confidence_score', 1.0) < 0.90:
            form['needs_review'] = True

        # Flag low-confidence fields
        for field in form.get('fields', []):
            ocr_data = field.get('ocr_data', {})
            if ocr_data.get('requires_review'):
                field['review_required'] = True

        forms.append(form)

    return forms
```

### Rendering with Style

```python
# Use style info in template
def render_form_preview(form, answers):
    style = form.get('style', {})

    template = env.get_template('styled_form.html')
    return template.render(
        form=form,
        answers=answers,
        header=style.get('header', {}),
        colors=style.get('colors', {}),
        layout=style.get('layout', {}),
        footer=style.get('footer', {})
    )
```

## Tools & Resources

### OCR Services

- [Google Cloud Vision API](https://cloud.google.com/vision/docs/ocr)
- [Azure Computer Vision](https://azure.microsoft.com/en-us/services/cognitive-services/computer-vision/)
- [AWS Textract](https://aws.amazon.com/textract/)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)

### Python Libraries

- `google-cloud-vision`: Google Vision API client
- `opencv-python`: Image preprocessing
- `Pillow`: Image manipulation
- `pytesseract`: Tesseract wrapper
- `pdf2image`: PDF to image conversion

### Form Template Libraries

- Government forms database
- Common business forms
- Healthcare forms
- Legal documents

## Future Enhancements

1. **AI-powered field detection**: Use ML models to identify field types
2. **Handwriting recognition**: Specialized models for handwritten forms
3. **Multi-language support**: Auto-detect form language
4. **Template learning**: Build form templates from multiple examples
5. **Batch processing**: Process multiple forms in parallel
6. **Quality metrics**: Track OCR accuracy over time
7. **Active learning**: Improve OCR from human corrections
