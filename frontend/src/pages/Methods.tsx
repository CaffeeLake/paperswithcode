import Header from "@/components/Header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

const methodCategories = [
  {
    name: "General",
    methods: [
      {
        id: "regularization",
        name: "Regularization",
        icon: "🔧",
        methodCount: 35,
        papersWithCode: 8337
      },
      {
        id: "stochastic-optimization",
        name: "Stochastic Optimization",
        icon: "📈",
        methodCount: 32,
        papersWithCode: 3816
      },
      {
        id: "attention",
        name: "Attention",
        icon: "🎯",
        methodCount: 31,
        papersWithCode: 4702
      },
      {
        id: "activation-functions",
        name: "Activation Functions",
        icon: "⚡",
        methodCount: 30,
        papersWithCode: 12018
      },
      {
        id: "normalization",
        name: "Normalization",
        icon: "📊",
        methodCount: 29,
        papersWithCode: 5087
      }
    ]
  },
  {
    name: "Computer Vision",
    methods: [
      {
        id: "convolutional-neural-networks",
        name: "Convolutional Neural Networks",
        icon: "🕸️",
        methodCount: 86,
        papersWithCode: 2449
      },
      {
        id: "image-model-blocks",
        name: "Image Model Blocks",
        icon: "🧩",
        methodCount: 72,
        papersWithCode: 3005
      },
      {
        id: "generative-models",
        name: "Generative Models",
        icon: "🎨",
        methodCount: 54,
        papersWithCode: 3730
      },
      {
        id: "object-detection-models",
        name: "Object Detection Models",
        icon: "👁️",
        methodCount: 34,
        papersWithCode: 833
      },
      {
        id: "image-feature-extractors",
        name: "Image Feature Extractors",
        icon: "🔍",
        methodCount: 27,
        papersWithCode: 52
      }
    ]
  }
];

const Methods = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />

      {/* Hero Section */}
      <div className="bg-gradient-to-br from-blue-600 to-blue-700 text-white py-16">
        <div className="container mx-auto px-4 text-center">
          <h1 className="text-5xl font-bold mb-4">Methods</h1>
          <p className="text-xl opacity-90 mb-2">🔬 825 machine learning components</p>
        </div>
      </div>

      {/* Description */}
      <div className="container mx-auto px-4 py-8 text-center">
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          A free and open resource that the community can edit and contribute to
        </p>
      </div>

      {/* Method Categories */}
      <div className="container mx-auto px-4 pb-12">
        {methodCategories.map((category) => (
          <div key={category.name} className="mb-12">
            <h2 className="text-3xl font-bold mb-6">{category.name}</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
              {category.methods.map((method) => (
                <Card key={method.id} className="hover:shadow-lg transition-shadow cursor-pointer">
                  <CardContent className="p-6">
                    <div className="flex items-start gap-3 mb-4">
                      <div className="text-3xl">{method.icon}</div>
                      <h3 className="text-lg font-semibold leading-tight">{method.name}</h3>
                    </div>

                    <div className="space-y-1 text-sm text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <span className="text-primary">🔬</span>
                        <span>{method.methodCount} methods</span>
                      </div>
                      <div>
                        <span>{method.papersWithCode.toLocaleString()} papers with code</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <div className="mt-6">
              <Button variant="link" className="text-primary hover:underline">
                ▶ See all {category.methods.length > 5 ? '52' : category.methods.length} categories
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Methods;
