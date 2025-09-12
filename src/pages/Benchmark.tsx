import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Dot } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import Header from "@/components/Header";
import { ArrowLeft, Trophy, Calendar } from "lucide-react";
import { useParams, Link } from "react-router-dom";

// Sample data for different benchmarks
const benchmarkData = {
  "wider-face-easy": {
    name: "Face Detection on WIDER Face (Easy)",
    metric: "Average Precision (AP)",
    allData: [
      { year: 2015, value: 61.3, model: "MTCNN", isSOTA: false },
      { year: 2016, value: 78.2, model: "HR", isSOTA: false },
      { year: 2017, value: 92.1, model: "S3FD", isSOTA: true },
      { year: 2018, value: 94.3, model: "PyramidBox", isSOTA: true },
      { year: 2019, value: 96.0, model: "DSFD", isSOTA: true },
      { year: 2020, value: 96.8, model: "RetinaFace", isSOTA: true },
      { year: 2021, value: 97.2, model: "SCRFD", isSOTA: true }
    ]
  },
  "wider-face-medium": {
    name: "Face Detection on WIDER Face (Medium)",
    metric: "Average Precision (AP)",
    allData: [
      { year: 2015, value: 59.8, model: "MTCNN", isSOTA: false },
      { year: 2016, value: 75.1, model: "HR", isSOTA: false },
      { year: 2017, value: 90.8, model: "S3FD", isSOTA: true },
      { year: 2018, value: 93.4, model: "PyramidBox", isSOTA: true },
      { year: 2019, value: 95.3, model: "DSFD", isSOTA: true },
      { year: 2020, value: 95.9, model: "RetinaFace", isSOTA: true },
      { year: 2021, value: 96.4, model: "SCRFD", isSOTA: true }
    ]
  },
  "wider-face-hard": {
    name: "Face Detection on WIDER Face (Hard)",
    metric: "Average Precision (AP)",
    allData: [
      { year: 2015, value: 32.1, model: "MTCNN", isSOTA: false },
      { year: 2016, value: 61.2, model: "HR", isSOTA: false },
      { year: 2017, value: 84.1, model: "S3FD", isSOTA: true },
      { year: 2018, value: 88.8, model: "PyramidBox", isSOTA: true },
      { year: 2019, value: 90.0, model: "DSFD", isSOTA: true },
      { year: 2020, value: 91.4, model: "RetinaFace", isSOTA: true },
      { year: 2021, value: 92.2, model: "SCRFD", isSOTA: true }
    ]
  },
  "fddb": {
    name: "Face Detection on FDDB",
    metric: "Average Precision (AP)",
    allData: [
      { year: 2015, value: 84.2, model: "MTCNN", isSOTA: false },
      { year: 2016, value: 87.5, model: "HR", isSOTA: false },
      { year: 2017, value: 93.7, model: "S3FD", isSOTA: true },
      { year: 2018, value: 96.6, model: "PyramidBox", isSOTA: true },
      { year: 2019, value: 99.1, model: "DSFD", isSOTA: true },
      { year: 2020, value: 99.3, model: "RetinaFace", isSOTA: true },
      { year: 2021, value: 99.5, model: "SCRFD", isSOTA: true }
    ]
  }
};

const CustomDot = (props: any) => {
  const { cx, cy, payload } = props;
  if (payload?.isSOTA) {
    return (
      <g>
        <Dot cx={cx} cy={cy} r={4} fill="#10B981" stroke="#10B981" strokeWidth={2} />
        <text x={cx} y={cy - 15} textAnchor="middle" className="fill-foreground text-xs font-medium">
          {payload.model}
        </text>
      </g>
    );
  }
  return <Dot cx={cx} cy={cy} r={2} fill="#94A3B8" />;
};

const Benchmark = () => {
  const { benchmark } = useParams();
  const currentBenchmark = benchmark || "wider-face-easy";
  const data = benchmarkData[currentBenchmark as keyof typeof benchmarkData];
  
  if (!data) {
    return <div>Benchmark not found</div>;
  }

  const sotaData = data.allData.filter(item => item.isSOTA);
  const allDataWithGaps = data.allData.map(item => ({
    ...item,
    sotaValue: item.isSOTA ? item.value : null
  }));
  
  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <main className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center space-x-2 text-sm text-muted-foreground mb-6">
          <Link to="/paper/1" className="hover:text-foreground transition-colors flex items-center space-x-1">
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
              <span>{data.metric} Progress Over Time</span>
              <div className="flex items-center space-x-4 text-sm">
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 bg-muted rounded-full"></div>
                  <span className="text-muted-foreground">Other models</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 bg-primary rounded-full"></div>
                  <span className="text-muted-foreground">State-of-the-art models</span>
                </div>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={allDataWithGaps} margin={{ top: 40, right: 30, left: 20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis 
                    dataKey="year" 
                    type="number"
                    scale="linear"
                    domain={['dataMin - 1', 'dataMax + 1']}
                    className="text-muted-foreground"
                  />
                  <YAxis 
                    domain={[30, 100]}
                    className="text-muted-foreground"
                    label={{ value: data.metric.toUpperCase(), angle: -90, position: 'insideLeft' }}
                  />
                  
                  {/* All points */}
                  <Line
                    dataKey="value"
                    stroke="transparent"
                    strokeWidth={0}
                    dot={<CustomDot />}
                  />
                  
                  {/* SOTA line */}
                  <Line
                    dataKey="sotaValue"
                    stroke="#10B981"
                    strokeWidth={3}
                    dot={false}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Current Rankings Table */}
        <Card>
          <CardHeader>
            <CardTitle>Current Top Models</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {sotaData
                .sort((a, b) => b.value - a.value)
                .slice(0, 5)
                .map((model, index) => (
                  <div key={model.model} className="flex items-center justify-between p-4 rounded-lg border border-border">
                    <div className="flex items-center space-x-4">
                      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary font-semibold">
                        {index + 1}
                      </div>
                      <div>
                        <h3 className="font-semibold">{model.model}</h3>
                        <p className="text-sm text-muted-foreground">Published {model.year}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-primary">{model.value}</div>
                      <p className="text-sm text-muted-foreground">{data.metric}</p>
                    </div>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default Benchmark;