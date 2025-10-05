# Method Images Feature

## Overview

The methods table now supports image URLs for displaying visual representations of AI/ML methods, such as architecture diagrams, workflow charts, or illustrations.

## Database Schema

### New Column
- **`image_url`**: VARCHAR(1000), nullable
  - Stores URL to an image/diagram representing the method
  - Examples: architecture diagrams, workflow charts, visual explanations
  - Recommended: Use high-quality images from official sources or CDNs

### Migration
- **File**: `backend/database/migration/add_image_url_to_methods.sql`
- **Date**: October 5, 2025
- **Applied**: Automatically by update script

## Model Updates

### SQLAlchemy Model (`backend/models/database.py`)
```python
class Method(Base):
    # ... other fields ...
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
```

### Pydantic API Model (`backend/models/api.py`)
```python
class Method(BaseModel):
    # ... other fields ...
    image_url: Optional[str] = Field(
        None,
        description="URL to an image/diagram representing the method"
    )
```

## Usage Examples

### Adding an Image to a Method

```python
import psycopg2

conn = psycopg2.connect(database="paperswithcode_hf", ...)
cur = conn.cursor()

cur.execute("""
    UPDATE methods
    SET image_url = %s
    WHERE name = %s
""", (
    "https://example.com/path/to/architecture-diagram.svg",
    "MethodName"
))

conn.commit()
```

### Querying Methods with Images

```python
# Get all methods that have images
cur.execute("""
    SELECT id, name, image_url
    FROM methods
    WHERE image_url IS NOT NULL
""")
```

### API Response

```json
{
  "id": "127",
  "name": "Whisper",
  "full_name": "Whisper",
  "description": "Whisper is an open-source machine learning model...",
  "area_id": "6",
  "source_url": "https://openai.com/index/whisper/",
  "image_url": "https://images.ctfassets.net/kftzwdyauwt9/d9c13138-366f-49d3-a1a563abddc1/8acfb590df46923b021026207ff1a438/asr-summary-of-model-architecture-desktop.svg?w=3840&q=90",
  "paper_count": 0
}
```

## Current Methods with Images

### Whisper
- **Name**: Whisper
- **Area**: Audio
- **Source**: https://openai.com/index/whisper/
- **Image**: https://images.ctfassets.net/kftzwdyauwt9/d9c13138-366f-49d3-a1a563abddc1/8acfb590df46923b021026207ff1a438/asr-summary-of-model-architecture-desktop.svg?w=3840&q=90
- **Description**: Speech recognition and transcription model architecture diagram from OpenAI

## Best Practices

### Image Sources
1. **Official Documentation**: Prefer images from official method documentation
2. **Research Papers**: Use figures from the original research paper (with proper attribution)
3. **CDN URLs**: Use stable CDN URLs that won't break
4. **SVG Format**: Prefer SVG for scalability and small file size
5. **High Resolution**: Ensure images are high-quality and readable

### Image Content
- Architecture diagrams showing model structure
- Workflow charts explaining the method's process
- Visual comparisons with other methods
- Key concepts or innovations illustrated

### URL Guidelines
- Use HTTPS URLs for security
- Ensure URLs are stable and won't expire
- Consider hosting critical images on your own CDN
- Verify image loading before committing to database
- Keep URLs under 1000 characters

## Frontend Integration

### Displaying Method Images

```typescript
// React component example
function MethodCard({ method }: { method: Method }) {
  return (
    <div className="method-card">
      <h3>{method.name}</h3>
      {method.image_url && (
        <img
          src={method.image_url}
          alt={`${method.name} architecture`}
          className="method-diagram"
        />
      )}
      <p>{method.description}</p>
    </div>
  );
}
```

### Loading States

```typescript
const [imageLoaded, setImageLoaded] = useState(false);

<img
  src={method.image_url}
  onLoad={() => setImageLoaded(true)}
  onError={() => console.error('Failed to load method image')}
  style={{ display: imageLoaded ? 'block' : 'none' }}
/>
```

## Maintenance

### Checking for Broken Images

```sql
-- Query methods with images (for verification)
SELECT id, name, image_url
FROM methods
WHERE image_url IS NOT NULL
ORDER BY name;
```

### Updating Images

```python
# Script to update method images
UPDATE methods
SET
    image_url = 'https://new-url.com/image.svg',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'MethodName';
```

## Future Enhancements

Potential improvements to consider:
- Multiple images per method (gallery support)
- Image metadata (caption, attribution, license)
- Thumbnail generation for large images
- Local image storage option
- Image validation on upload
- Automatic image optimization
