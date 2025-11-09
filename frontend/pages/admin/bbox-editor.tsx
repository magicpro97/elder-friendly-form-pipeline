import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import axios from "axios";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
  page: number;
}

interface Field {
  id: string;
  label: string;
  type: string;
  bbox: BBox | null;
}

interface FormData {
  formId: string;
  title: string;
  fields: Field[];
  pages: number;
  pdfUrl: string;
  bboxDetection?: {
    field_positions?: Array<{
      field_id: string;
      bbox: BBox;
      confidence: number;
      auto_detected: boolean;
    }>;
    image_width?: number;
    image_height?: number;
  };
}

export default function BboxEditor() {
  const router = useRouter();
  const { formId } = router.query;

  const [formData, setFormData] = useState<FormData | null>(null);
  const [selectedField, setSelectedField] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [startPos, setStartPos] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [scale, setScale] = useState(1);
  const [saving, setSaving] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pdfImageRef = useRef<HTMLImageElement>(null);

  // Load form data
  useEffect(() => {
    if (!formId) return;

    const loadFormData = async () => {
      try {
        const response = await axios.get(
          `${API_BASE_URL}/admin/forms/${formId}/bbox-editor`,
        );
        setFormData(response.data);
      } catch (error) {
        console.error("Failed to load form data:", error);
        alert("Không thể tải dữ liệu form");
      }
    };

    loadFormData();
  }, [formId]);

  // Render PDF and bbox overlay
  useEffect(() => {
    if (!formData || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Load PDF preview image (PNG converted from PDF)
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = `${API_BASE_URL}/admin/forms/${formId}/preview?page=1&t=${Date.now()}`;

    img.onload = () => {
      pdfImageRef.current = img;

      // Set canvas size - fixed width, maintain aspect ratio
      const maxWidth = 900;
      const calculatedScale = maxWidth / img.width;
      setScale(calculatedScale);

      canvas.width = img.width * calculatedScale;
      canvas.height = img.height * calculatedScale;

      // Draw image
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // Draw existing bbox
      drawAllBbox(ctx, calculatedScale);
    };

    img.onerror = (error) => {
      console.error("Failed to load preview image:", error);
      alert("Không thể hiển thị preview. Vui lòng kiểm tra API.");
    };
  }, [formData, formId]);

  const drawAllBbox = (ctx: CanvasRenderingContext2D, currentScale: number) => {
    if (!formData) return;

    formData.fields.forEach((field) => {
      if (field.bbox) {
        const isSelected = field.id === selectedField;

        ctx.strokeStyle = isSelected ? "#ff0000" : "#00ff00";
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.strokeRect(
          field.bbox.x * currentScale,
          field.bbox.y * currentScale,
          field.bbox.width * currentScale,
          field.bbox.height * currentScale,
        );

        // Label
        ctx.fillStyle = isSelected ? "#ff0000" : "#00ff00";
        ctx.font = "12px Arial";
        ctx.fillText(
          field.label,
          field.bbox.x * currentScale,
          field.bbox.y * currentScale - 5,
        );
      }
    });
  };

  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!selectedField || !canvasRef.current) return;

    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / scale;
    const y = (e.clientY - rect.top) / scale;

    setStartPos({ x, y });
    setDrawing(true);
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawing || !startPos || !canvasRef.current || !selectedField) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Check if PDF image is loaded
    const pdfImage = pdfImageRef.current;
    if (!pdfImage || !pdfImage.complete || pdfImage.naturalWidth === 0) {
      console.warn("PDF image not loaded yet");
      return;
    }

    // Redraw PDF
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(pdfImage, 0, 0, canvas.width, canvas.height);

    // Redraw existing bbox
    drawAllBbox(ctx, scale);

    // Draw current selection
    const rect = canvas.getBoundingClientRect();
    const currentX = (e.clientX - rect.left) / scale;
    const currentY = (e.clientY - rect.top) / scale;

    ctx.strokeStyle = "#ff00ff";
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(
      startPos.x * scale,
      startPos.y * scale,
      (currentX - startPos.x) * scale,
      (currentY - startPos.y) * scale,
    );
    ctx.setLineDash([]);
  };

  const handleCanvasMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawing || !startPos || !selectedField || !formData) return;

    const rect = canvasRef.current!.getBoundingClientRect();
    const endX = (e.clientX - rect.left) / scale;
    const endY = (e.clientY - rect.top) / scale;

    // Calculate bbox
    const bbox: BBox = {
      x: Math.min(startPos.x, endX),
      y: Math.min(startPos.y, endY),
      width: Math.abs(endX - startPos.x),
      height: Math.abs(endY - startPos.y),
      page: 1,
    };

    // Update field bbox locally
    const updatedFields = formData.fields.map((field) => {
      if (field.id === selectedField) {
        return { ...field, bbox };
      }
      return field;
    });

    setFormData({ ...formData, fields: updatedFields });

    setDrawing(false);
    setStartPos(null);

    // Redraw
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(pdfImageRef.current!, 0, 0, canvas.width, canvas.height);
    drawAllBbox(ctx, scale);
  };

  const handleSave = async () => {
    if (!formData) return;

    setSaving(true);

    try {
      const updates = formData.fields
        .filter((field) => field.bbox !== null)
        .map((field) => ({
          field_id: field.id,
          bbox: field.bbox!,
        }));

      await axios.post(`${API_BASE_URL}/admin/forms/${formId}/bbox`, updates);

      alert("✅ Đã lưu vị trí thành công!");
    } catch (error) {
      console.error("Failed to save bbox:", error);
      alert("❌ Lưu thất bại");
    } finally {
      setSaving(false);
    }
  };

  const handleAutoApply = () => {
    if (!formData?.bboxDetection?.field_positions) {
      alert("Không có dữ liệu tự động phát hiện");
      return;
    }

    const detectedMap = new Map(
      formData.bboxDetection.field_positions.map((fp) => [
        fp.field_id,
        fp.bbox,
      ]),
    );

    const updatedFields = formData.fields.map((field) => {
      if (detectedMap.has(field.id)) {
        return { ...field, bbox: detectedMap.get(field.id)! };
      }
      return field;
    });

    setFormData({ ...formData, fields: updatedFields });

    // Redraw
    setTimeout(() => {
      const canvas = canvasRef.current!;
      const ctx = canvas.getContext("2d")!;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (pdfImageRef.current) {
        ctx.drawImage(pdfImageRef.current, 0, 0, canvas.width, canvas.height);
        drawAllBbox(ctx, scale);
      }
    }, 100);
  };

  if (!formData) {
    return (
      <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
        <h1>Đang tải...</h1>
      </div>
    );
  }

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif" }}>
      <h1>📐 Bbox Editor: {formData.title}</h1>

      <div style={{ display: "flex", gap: "20px", marginTop: "20px" }}>
        {/* Sidebar - Field List */}
        <div
          style={{
            width: "300px",
            border: "1px solid #ccc",
            padding: "10px",
            borderRadius: "8px",
          }}
        >
          <h3>Danh sách trường</h3>

          {formData.bboxDetection?.field_positions && (
            <button
              onClick={handleAutoApply}
              style={{
                marginBottom: "15px",
                padding: "10px",
                width: "100%",
                backgroundColor: "#4CAF50",
                color: "white",
                border: "none",
                borderRadius: "5px",
                cursor: "pointer",
              }}
            >
              ✨ Áp dụng tự động (
              {formData.bboxDetection.field_positions.length} trường)
            </button>
          )}

          {formData.fields.map((field) => (
            <div
              key={field.id}
              onClick={() => setSelectedField(field.id)}
              style={{
                padding: "10px",
                marginBottom: "8px",
                border:
                  selectedField === field.id
                    ? "2px solid #ff0000"
                    : "1px solid #ddd",
                borderRadius: "5px",
                cursor: "pointer",
                backgroundColor: field.bbox ? "#e8f5e9" : "#fff3e0",
              }}
            >
              <div style={{ fontWeight: "bold" }}>{field.label}</div>
              <div style={{ fontSize: "12px", color: "#666" }}>
                {field.bbox ? "✅ Đã có bbox" : "⚠️ Chưa có bbox"}
              </div>
            </div>
          ))}

          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              marginTop: "20px",
              padding: "12px",
              width: "100%",
              backgroundColor: "#2196F3",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: saving ? "not-allowed" : "pointer",
              fontSize: "16px",
              fontWeight: "bold",
            }}
          >
            {saving ? "⏳ Đang lưu..." : "💾 Lưu tất cả"}
          </button>
        </div>

        {/* Canvas - PDF Viewer */}
        <div style={{ flex: 1 }}>
          <div
            style={{
              marginBottom: "10px",
              padding: "10px",
              backgroundColor: "#f5f5f5",
              borderRadius: "5px",
            }}
          >
            <strong>Hướng dẫn:</strong>
            <ol style={{ marginTop: "5px", paddingLeft: "20px" }}>
              <li>Chọn trường từ danh sách bên trái</li>
              <li>Nhấn giữ chuột và kéo trên PDF để đánh dấu vị trí</li>
              <li>Nhấn "Lưu tất cả" khi hoàn thành</li>
            </ol>
            {selectedField && (
              <div
                style={{
                  marginTop: "10px",
                  color: "#ff0000",
                  fontWeight: "bold",
                }}
              >
                📍 Đang chọn:{" "}
                {formData.fields.find((f) => f.id === selectedField)?.label}
              </div>
            )}
          </div>

          <canvas
            ref={canvasRef}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            style={{
              border: "2px solid #333",
              cursor: selectedField ? "crosshair" : "default",
              borderRadius: "5px",
            }}
          />
        </div>
      </div>
    </div>
  );
}
