import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Dot } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import Header from "@/components/Header";
import { ArrowLeft, Trophy, Calendar, Github, ExternalLink, CheckCircle } from "lucide-react";
import { useParams, Link } from "react-router-dom";
import { useState } from "react";

// Sample data for different benchmarks
const benchmarkData = {
  "wider-face-easy": {
    name: "Face Detection on WIDER Face (Easy)",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2015,
        value: 61.3,
        model: "MTCNN",
        isSOTA: false,
        paperTitle: "Joint Face Detection and Alignment using Multi-task CNN",
        paperUrl: "/paper/2509.21114",
        codeUrl: "https://github.com/kpzhang93/MTCNN_face_detection_alignment",
        hasCode: true,
        isVerified: false,
        tags: ["CNN", "Multi-task"]
      },
      {
        year: 2016,
        value: 78.2,
        model: "HR",
        isSOTA: false,
        paperTitle: "Finding Tiny Faces",
        paperUrl: "/paper/2509.20706",
        codeUrl: "https://github.com/peiyunh/tiny",
        hasCode: true,
        isVerified: true,
        tags: ["Scale", "Resolution"]
      },
      {
        year: 2017,
        value: 92.1,
        model: "S3FD",
        isSOTA: true,
        paperTitle: "S3FD: Single Shot Scale-invariant Face Detector",
        paperUrl: "/paper/2509.21106",
        codeUrl: "https://github.com/sfzhang15/SFD",
        hasCode: true,
        isVerified: true,
        tags: ["Single Shot", "Scale-invariant"]
      },
      {
        year: 2018,
        value: 94.3,
        model: "PyramidBox",
        isSOTA: true,
        paperTitle: "PyramidBox: A Context-assisted Single Shot Face Detector",
        paperUrl: "/paper/2509.21317",
        codeUrl: "https://github.com/EricZgw/PyramidBox",
        hasCode: true,
        isVerified: true,
        tags: ["Context", "Pyramid"]
      },
      {
        year: 2019,
        value: 96.0,
        model: "DSFD",
        isSOTA: true,
        paperTitle: "DSFD: Dual Shot Face Detector",
        paperUrl: "/paper/2509.20878",
        codeUrl: "https://github.com/TencentYoutuResearch/FaceDetection-DSFD",
        hasCode: true,
        isVerified: true,
        tags: ["Dual Shot", "Feature Enhancement"]
      },
      {
        year: 2020,
        value: 96.8,
        model: "RetinaFace",
        isSOTA: true,
        paperTitle: "RetinaFace: Single-Shot Multi-Level Face Localisation in the Wild",
        paperUrl: "/paper/2509.21138",
        codeUrl: "https://github.com/deepinsight/insightface",
        hasCode: true,
        isVerified: true,
        tags: ["Multi-level", "Landmarks"]
      },
      {
        year: 2021,
        value: 97.2,
        model: "SCRFD",
        isSOTA: true,
        paperTitle: "Sample and Computation Redistribution for Efficient Face Detection",
        paperUrl: "/paper/2509.21320",
        codeUrl: "https://github.com/deepinsight/insightface/tree/master/detection/scrfd",
        hasCode: true,
        isVerified: true,
        tags: ["Efficient", "Redistribution"]
      }
    ]
  },
  "wider-face-medium": {
    name: "Face Detection on WIDER Face (Medium)",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2015,
        value: 59.8,
        model: "MTCNN",
        isSOTA: false,
        paperTitle: "Joint Face Detection and Alignment using Multi-task CNN",
        paperUrl: "/paper/2509.21114",
        codeUrl: "https://github.com/kpzhang93/MTCNN_face_detection_alignment",
        hasCode: true,
        isVerified: false,
        tags: ["CNN", "Multi-task"]
      },
      {
        year: 2016,
        value: 75.1,
        model: "HR",
        isSOTA: false,
        paperTitle: "Finding Tiny Faces",
        paperUrl: "/paper/2509.20706",
        codeUrl: "https://github.com/peiyunh/tiny",
        hasCode: true,
        isVerified: true,
        tags: ["Scale", "Resolution"]
      },
      {
        year: 2017,
        value: 90.8,
        model: "S3FD",
        isSOTA: true,
        paperTitle: "S3FD: Single Shot Scale-invariant Face Detector",
        paperUrl: "/paper/2509.21106",
        codeUrl: "https://github.com/sfzhang15/SFD",
        hasCode: true,
        isVerified: true,
        tags: ["Single Shot", "Scale-invariant"]
      },
      {
        year: 2018,
        value: 93.4,
        model: "PyramidBox",
        isSOTA: true,
        paperTitle: "PyramidBox: A Context-assisted Single Shot Face Detector",
        paperUrl: "/paper/2509.21317",
        codeUrl: "https://github.com/EricZgw/PyramidBox",
        hasCode: true,
        isVerified: true,
        tags: ["Context", "Pyramid"]
      },
      {
        year: 2019,
        value: 95.3,
        model: "DSFD",
        isSOTA: true,
        paperTitle: "DSFD: Dual Shot Face Detector",
        paperUrl: "/paper/2509.20878",
        codeUrl: "https://github.com/TencentYoutuResearch/FaceDetection-DSFD",
        hasCode: true,
        isVerified: true,
        tags: ["Dual Shot", "Feature Enhancement"]
      },
      {
        year: 2020,
        value: 95.9,
        model: "RetinaFace",
        isSOTA: true,
        paperTitle: "RetinaFace: Single-Shot Multi-Level Face Localisation in the Wild",
        paperUrl: "/paper/2509.21138",
        codeUrl: "https://github.com/deepinsight/insightface",
        hasCode: true,
        isVerified: true,
        tags: ["Multi-level", "Landmarks"]
      },
      {
        year: 2021,
        value: 96.4,
        model: "SCRFD",
        isSOTA: true,
        paperTitle: "Sample and Computation Redistribution for Efficient Face Detection",
        paperUrl: "/paper/2509.21320",
        codeUrl: "https://github.com/deepinsight/insightface/tree/master/detection/scrfd",
        hasCode: true,
        isVerified: true,
        tags: ["Efficient", "Redistribution"]
      }
    ]
  },
  "wider-face-hard": {
    name: "Face Detection on WIDER Face (Hard)",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2015,
        value: 32.1,
        model: "MTCNN",
        isSOTA: false,
        paperTitle: "Joint Face Detection and Alignment using Multi-task CNN",
        paperUrl: "/paper/2509.21114",
        codeUrl: "https://github.com/kpzhang93/MTCNN_face_detection_alignment",
        hasCode: true,
        isVerified: false,
        tags: ["CNN", "Multi-task"]
      },
      {
        year: 2016,
        value: 61.2,
        model: "HR",
        isSOTA: false,
        paperTitle: "Finding Tiny Faces",
        paperUrl: "/paper/2509.20706",
        codeUrl: "https://github.com/peiyunh/tiny",
        hasCode: true,
        isVerified: true,
        tags: ["Scale", "Resolution"]
      },
      {
        year: 2017,
        value: 84.1,
        model: "S3FD",
        isSOTA: true,
        paperTitle: "S3FD: Single Shot Scale-invariant Face Detector",
        paperUrl: "/paper/2509.21106",
        codeUrl: "https://github.com/kpzhang93/SFD",
        hasCode: true,
        isVerified: true,
        tags: ["Single Shot", "Scale-invariant"]
      },
      {
        year: 2018,
        value: 88.8,
        model: "PyramidBox",
        isSOTA: true,
        paperTitle: "PyramidBox: A Context-assisted Single Shot Face Detector",
        paperUrl: "/paper/2509.21317",
        codeUrl: "https://github.com/EricZgw/PyramidBox",
        hasCode: true,
        isVerified: true,
        tags: ["Context", "Pyramid"]
      },
      {
        year: 2019,
        value: 90.0,
        model: "DSFD",
        isSOTA: true,
        paperTitle: "DSFD: Dual Shot Face Detector",
        paperUrl: "/paper/2509.20878",
        codeUrl: "https://github.com/TencentYoutuResearch/FaceDetection-DSFD",
        hasCode: true,
        isVerified: true,
        tags: ["Dual Shot", "Feature Enhancement"]
      },
      {
        year: 2020,
        value: 91.4,
        model: "RetinaFace",
        isSOTA: true,
        paperTitle: "RetinaFace: Single-Shot Multi-Level Face Localisation in the Wild",
        paperUrl: "/paper/2509.21138",
        codeUrl: "https://github.com/deepinsight/insightface",
        hasCode: true,
        isVerified: true,
        tags: ["Multi-level", "Landmarks"]
      },
      {
        year: 2021,
        value: 92.2,
        model: "SCRFD",
        isSOTA: true,
        paperTitle: "Sample and Computation Redistribution for Efficient Face Detection",
        paperUrl: "/paper/2509.21320",
        codeUrl: "https://github.com/deepinsight/insightface/tree/master/detection/scrfd",
        hasCode: true,
        isVerified: true,
        tags: ["Efficient", "Redistribution"]
      }
    ]
  },
  "fddb": {
    name: "Face Detection on FDDB",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2015,
        value: 84.2,
        model: "MTCNN",
        isSOTA: false,
        paperTitle: "Joint Face Detection and Alignment using Multi-task CNN",
        paperUrl: "/paper/2509.21114",
        codeUrl: "https://github.com/kpzhang93/MTCNN_face_detection_alignment",
        hasCode: true,
        isVerified: false,
        tags: ["CNN", "Multi-task"]
      },
      {
        year: 2016,
        value: 87.5,
        model: "HR",
        isSOTA: false,
        paperTitle: "Finding Tiny Faces",
        paperUrl: "/paper/2509.20706",
        codeUrl: "https://github.com/peiyunh/tiny",
        hasCode: true,
        isVerified: true,
        tags: ["Scale", "Resolution"]
      },
      {
        year: 2017,
        value: 93.7,
        model: "S3FD",
        isSOTA: true,
        paperTitle: "S3FD: Single Shot Scale-invariant Face Detector",
        paperUrl: "/paper/2509.21106",
        codeUrl: "https://github.com/sfzhang15/SFD",
        hasCode: true,
        isVerified: true,
        tags: ["Single Shot", "Scale-invariant"]
      },
      {
        year: 2018,
        value: 96.6,
        model: "PyramidBox",
        isSOTA: true,
        paperTitle: "PyramidBox: A Context-assisted Single Shot Face Detector",
        paperUrl: "/paper/2509.21317",
        codeUrl: "https://github.com/EricZgw/PyramidBox",
        hasCode: true,
        isVerified: true,
        tags: ["Context", "Pyramid"]
      },
      {
        year: 2019,
        value: 99.1,
        model: "DSFD",
        isSOTA: true,
        paperTitle: "DSFD: Dual Shot Face Detector",
        paperUrl: "/paper/2509.20878",
        codeUrl: "https://github.com/TencentYoutuResearch/FaceDetection-DSFD",
        hasCode: true,
        isVerified: true,
        tags: ["Dual Shot", "Feature Enhancement"]
      },
      {
        year: 2020,
        value: 99.3,
        model: "RetinaFace",
        isSOTA: true,
        paperTitle: "RetinaFace: Single-Shot Multi-Level Face Localisation in the Wild",
        paperUrl: "/paper/2509.21138",
        codeUrl: "https://github.com/deepinsight/insightface",
        hasCode: true,
        isVerified: true,
        tags: ["Multi-level", "Landmarks"]
      },
      {
        year: 2021,
        value: 99.5,
        model: "SCRFD",
        isSOTA: true,
        paperTitle: "Sample and Computation Redistribution for Efficient Face Detection",
        paperUrl: "/paper/2509.21320",
        codeUrl: "https://github.com/deepinsight/insightface/tree/master/detection/scrfd",
        hasCode: true,
        isVerified: true,
        tags: ["Efficient", "Redistribution"]
      }
    ]
  },
  "coco-test-dev": {
    name: "Object Detection on COCO test-dev",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2017,
        value: 39.1,
        model: "Mask R-CNN",
        isSOTA: false,
        paperTitle: "Mask R-CNN",
        paperUrl: "/paper/2509.21268",
        codeUrl: "https://github.com/facebookresearch/maskrcnn-benchmark",
        hasCode: true,
        isVerified: true,
        tags: ["Two-stage", "Instance Segmentation"]
      },
      {
        year: 2019,
        value: 48.4,
        model: "EfficientDet-D7",
        isSOTA: false,
        paperTitle: "EfficientDet: Scalable and Efficient Object Detection",
        paperUrl: "/paper/2509.21240",
        codeUrl: "https://github.com/google/automl/tree/master/efficientdet",
        hasCode: true,
        isVerified: true,
        tags: ["Efficient", "Compound Scaling"]
      },
      {
        year: 2021,
        value: 57.1,
        model: "Cascade Eff-B7 NAS-FPN",
        isSOTA: true,
        paperTitle: "Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segmentation",
        paperUrl: "/paper/2509.21245",
        codeUrl: "https://github.com/google-research/deeplab2",
        hasCode: true,
        isVerified: true,
        tags: ["Data Augmentation", "Copy-Paste", "NAS-FPN"]
      }
    ]
  },
  "coco-minival": {
    name: "Object Detection on COCO minival",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2017,
        value: 37.1,
        model: "Mask R-CNN",
        isSOTA: false,
        paperTitle: "Mask R-CNN",
        paperUrl: "/paper/2509.21268",
        codeUrl: "https://github.com/facebookresearch/maskrcnn-benchmark",
        hasCode: true,
        isVerified: true,
        tags: ["Two-stage", "Instance Segmentation"]
      },
      {
        year: 2021,
        value: 55.2,
        model: "Cascade Eff-B7 NAS-FPN",
        isSOTA: true,
        paperTitle: "Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segmentation",
        paperUrl: "/paper/2509.21245",
        codeUrl: "https://github.com/google-research/deeplab2",
        hasCode: true,
        isVerified: true,
        tags: ["Data Augmentation", "Copy-Paste", "NAS-FPN"]
      }
    ]
  },
  "pascal-voc-2007": {
    name: "Object Detection on PASCAL VOC 2007",
    metric: "Mean Average Precision (mAP)",
    allData: [
      {
        year: 2016,
        value: 73.2,
        model: "SSD",
        isSOTA: false,
        paperTitle: "SSD: Single Shot MultiBox Detector",
        paperUrl: "/paper/2509.21114",
        codeUrl: "https://github.com/weiliu89/caffe/tree/ssd",
        hasCode: true,
        isVerified: true,
        tags: ["Single Shot", "MultiBox"]
      },
      {
        year: 2021,
        value: 89.4,
        model: "Cascade Eff-B7 NAS-FPN",
        isSOTA: true,
        paperTitle: "Simple Copy-Paste is a Strong Data Augmentation Method for Instance Segmentation",
        paperUrl: "/paper/2509.21245",
        codeUrl: "https://github.com/google-research/deeplab2",
        hasCode: true,
        isVerified: true,
        tags: ["Data Augmentation", "Copy-Paste", "NAS-FPN"]
      }
    ]
  },
  "kitti-cars-easy": {
    name: "3D Object Detection on KITTI Cars Easy",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2019,
        value: 88.4,
        model: "PointRCNN",
        isSOTA: false,
        paperTitle: "PointRCNN: 3D Object Detection from Raw Point Cloud",
        paperUrl: "/paper/2509.20706",
        codeUrl: "https://github.com/sshaoshuai/PointRCNN",
        hasCode: true,
        isVerified: true,
        tags: ["Point Cloud", "3D Detection"]
      },
      {
        year: 2021,
        value: 92.8,
        model: "Patches",
        isSOTA: true,
        paperTitle: "Patch Refinement -- Localized 3D Object Detection",
        paperUrl: "/paper/2509.21106",
        codeUrl: "https://github.com/filipstoklasa/patches",
        hasCode: true,
        isVerified: true,
        tags: ["3D Detection", "Patch Refinement", "Localized"]
      }
    ]
  },
  "crowdhuman-full-body": {
    name: "Object Detection on CrowdHuman (Full Body)",
    metric: "Average Precision (AP)",
    allData: [
      {
        year: 2019,
        value: 84.9,
        model: "Faster R-CNN",
        isSOTA: false,
        paperTitle: "Faster R-CNN: Towards Real-Time Object Detection with Region Proposal Networks",
        paperUrl: "/paper/2509.21317",
        codeUrl: "https://github.com/rbgirshick/py-faster-rcnn",
        hasCode: true,
        isVerified: true,
        tags: ["Two-stage", "Region Proposal"]
      },
      {
        year: 2021,
        value: 91.4,
        model: "IterDet (Faster RCNN, ResNet50, 2 iterations)",
        isSOTA: true,
        paperTitle: "IterDet: Iterative Scheme for ObjectDetection in Crowded Environments",
        paperUrl: "/paper/2509.20878",
        codeUrl: "https://github.com/yuantn/IterDet",
        hasCode: true,
        isVerified: true,
        tags: ["Iterative", "Crowded Scenes", "ResNet50"]
      }
    ]
  },
  "imagenet": {
    name: "Image Classification on ImageNet",
    metric: "Top-1 Accuracy (%)",
    allData: [
      {
        year: 2015,
        value: 76.3,
        model: "ResNet-152",
        isSOTA: false,
        paperTitle: "Deep Residual Learning for Image Recognition",
        paperUrl: "/paper/2509.21138",
        codeUrl: "https://github.com/KaimingHe/deep-residual-networks",
        hasCode: true,
        isVerified: true,
        tags: ["Residual", "Deep Learning"]
      },
      {
        year: 2020,
        value: 88.5,
        model: "Vision Transformer (ViT-H/14)",
        isSOTA: true,
        paperTitle: "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
        paperUrl: "/paper/2509.21320",
        codeUrl: "https://github.com/google-research/vision_transformer",
        hasCode: true,
        isVerified: true,
        tags: ["Vision Transformer", "Attention", "Self-Attention"]
      }
    ]
  }
};

const CustomDot = (props: any) => {
  const { cx, cy, payload } = props;
  if (payload?.isSOTA) {
    return (
      <g>
        <Dot cx={cx} cy={cy} r={5} fill="#0EA5E9" stroke="#0EA5E9" strokeWidth={2} />
        <text x={cx} y={cy - 20} textAnchor="middle" className="fill-foreground text-xs font-medium">
          {payload.model}
        </text>
      </g>
    );
  }
  return <Dot cx={cx} cy={cy} r={3} fill="#9CA3AF" stroke="#9CA3AF" strokeWidth={1} />;
};

const formatXAxisTick = (value: number) => {
  const date = new Date(value, 0, 1);
  return date.getFullYear().toString().slice(-2);
};

const Benchmark = () => {
  const { benchmark } = useParams();
  const currentBenchmark = benchmark || "wider-face-easy";
  const data = benchmarkData[currentBenchmark as keyof typeof benchmarkData];

  const [selectedMetric, setSelectedMetric] = useState("Average Precision (AP)");
  const [selectedModels, setSelectedModels] = useState("all");
  const [viewBy, setViewBy] = useState("date");

  if (!data) {
    return <div>Benchmark not found</div>;
  }

  const metrics = ["Average Precision (AP)", "F1-Score", "Recall"];
  const modelOptions = ["all", "sota-only", "recent"];

  const filteredData = data.allData.filter(item => {
    if (selectedModels === "sota-only") return item.isSOTA;
    if (selectedModels === "recent") return item.year >= 2019;
    return true;
  });

  const allDataWithGaps = filteredData.map(item => ({
    ...item,
    sotaValue: item.isSOTA ? item.value : null
  }));

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center space-x-2 text-sm text-muted-foreground mb-6">
          <Link to="/paper/2509.21320" className="hover:text-foreground transition-colors flex items-center space-x-1">
            <ArrowLeft className="w-4 h-4" />
            <span>Back to paper</span>
          </Link>
          <span>/</span>
          <span className="text-foreground">Benchmark Results</span>
        </div>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-4">
            <Trophy className="w-6 h-6 text-yellow-600" />
            <h1 className="text-3xl font-bold">{data.name}</h1>
          </div>

          <div className="flex items-center space-x-4 text-sm text-muted-foreground">
            <Badge variant="secondary" className="bg-primary/10 text-primary">
              State-of-the-Art Leaderboard
            </Badge>
            <div className="flex items-center space-x-1">
              <Calendar className="w-4 h-4" />
              <span>Updated {new Date().toLocaleDateString()}</span>
            </div>
          </div>
        </div>

        {/* Benchmark Tabs */}
        <Tabs value={currentBenchmark} className="mb-8">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="wider-face-easy" asChild>
              <Link to="/benchmark/wider-face-easy">WIDER Face (Easy)</Link>
            </TabsTrigger>
            <TabsTrigger value="wider-face-medium" asChild>
              <Link to="/benchmark/wider-face-medium">WIDER Face (Medium)</Link>
            </TabsTrigger>
            <TabsTrigger value="wider-face-hard" asChild>
              <Link to="/benchmark/wider-face-hard">WIDER Face (Hard)</Link>
            </TabsTrigger>
            <TabsTrigger value="fddb" asChild>
              <Link to="/benchmark/fddb">FDDB</Link>
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Chart */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Leaderboard</span>
              <div className="flex items-center space-x-4 text-sm">
                <div className="flex items-center space-x-2">
                  <span className="text-muted-foreground">View</span>
                  <Select value={selectedMetric} onValueChange={setSelectedMetric}>
                    <SelectTrigger className="w-40">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {metrics.map((metric) => (
                        <SelectItem key={metric} value={metric}>
                          {metric}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-muted-foreground">by</span>
                  <Select value={viewBy} onValueChange={setViewBy}>
                    <SelectTrigger className="w-20">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="date">Date</SelectItem>
                      <SelectItem value="model">Model</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-muted-foreground">for</span>
                  <Select value={selectedModels} onValueChange={setSelectedModels}>
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All models</SelectItem>
                      <SelectItem value="sota-only">SOTA only</SelectItem>
                      <SelectItem value="recent">Recent models</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={allDataWithGaps} margin={{ top: 40, right: 30, left: 20, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted/30" />
                  <XAxis
                    dataKey="year"
                    type="number"
                    scale="linear"
                    domain={['dataMin - 0.5', 'dataMax + 0.5']}
                    tickFormatter={formatXAxisTick}
                    className="text-muted-foreground text-xs"
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[30, 100]}
                    className="text-muted-foreground text-xs"
                    label={{
                      value: selectedMetric.toUpperCase(),
                      angle: -90,
                      position: 'insideLeft',
                      style: { textAnchor: 'middle' }
                    }}
                    axisLine={false}
                    tickLine={false}
                  />

                  {/* All points */}
                  <Line
                    dataKey="value"
                    stroke="transparent"
                    strokeWidth={0}
                    dot={<CustomDot />}
                    activeDot={false}
                  />

                  {/* SOTA line */}
                  <Line
                    dataKey="sotaValue"
                    stroke="#0EA5E9"
                    strokeWidth={3}
                    dot={false}
                    connectNulls={false}
                    activeDot={{ r: 6, fill: "#0EA5E9" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Legend */}
            <div className="flex items-center justify-center space-x-6 mt-4 text-sm">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-muted rounded-full"></div>
                <span className="text-muted-foreground">Other models</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-sky-500 rounded-full"></div>
                <span className="text-muted-foreground">Models with highest {selectedMetric}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Current Rankings Table */}
        <Card>
          <CardHeader>
            <CardTitle>Leaderboard</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-2 font-medium text-muted-foreground">Rank</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Model</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">{data.metric}</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Paper</th>
                    <th className="text-center py-3 px-2 font-medium text-muted-foreground">Code</th>
                    <th className="text-center py-3 px-2 font-medium text-muted-foreground">Result</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Year</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Tags</th>
                  </tr>
                </thead>
                <tbody>
                  {data.allData
                    .sort((a, b) => b.value - a.value)
                    .map((model, index) => (
                      <tr key={model.model} className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-2">
                          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-muted text-sm font-medium">
                            {index + 1}
                          </div>
                        </td>
                        <td className="py-4 px-4">
                          <div className="font-semibold">{model.model}</div>
                        </td>
                        <td className="py-4 px-4">
                          <div className="font-semibold text-lg">{model.value}</div>
                        </td>
                        <td className="py-4 px-4">
                          <Link
                            to={model.paperUrl}
                            className="text-primary hover:underline text-sm max-w-xs block truncate"
                            title={model.paperTitle}
                          >
                            {model.paperTitle}
                          </Link>
                        </td>
                        <td className="py-4 px-2 text-center">
                          {model.hasCode && (
                            <a
                              href={model.codeUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-muted hover:bg-muted/80 transition-colors"
                            >
                              <Github className="w-4 h-4" />
                            </a>
                          )}
                        </td>
                        <td className="py-4 px-2 text-center">
                          {model.isVerified && (
                            <CheckCircle className="w-5 h-5 text-green-600 mx-auto" />
                          )}
                        </td>
                        <td className="py-4 px-4 text-muted-foreground">
                          {model.year}
                        </td>
                        <td className="py-4 px-4">
                          <div className="flex flex-wrap gap-1">
                            {model.tags.map((tag, tagIndex) => (
                              <Badge key={tagIndex} variant="secondary" className="text-xs">
                                {tag}
                              </Badge>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default Benchmark;
