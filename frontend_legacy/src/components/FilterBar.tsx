import { Calendar, TrendingUp, Settings, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const FilterBar = () => {
  return (
    <div className="flex flex-col space-y-4 mb-8">
      {/* Main Title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Daily Papers</h1>
          <p className="text-muted-foreground mt-1">
            by <span className="font-medium">AI Research Community</span> and researchers worldwide
          </p>
        </div>
        <Button variant="outline" size="sm">
          + Submit a paper
        </Button>
      </div>

      {/* Filters and Navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          {/* Time Period Filters */}
          <div className="flex items-center space-x-1 bg-muted/50 rounded-lg p-1">
            <Button variant="default" size="sm" className="h-8 px-3">
              Daily
            </Button>
            <Button variant="ghost" size="sm" className="h-8 px-3">
              Weekly
            </Button>
            <Button variant="ghost" size="sm" className="h-8 px-3">
              Monthly
            </Button>
          </div>

          {/* Trending Badge */}
          <Badge variant="secondary" className="bg-paper-orange/10 text-paper-orange border-paper-orange/20">
            <TrendingUp className="w-3 h-3 mr-1" />
            Trending
          </Badge>
        </div>

        {/* Date Navigation */}
        <div className="flex items-center space-x-2">
          <Button variant="outline" size="icon" className="h-8 w-8">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <div className="flex items-center space-x-2 px-3 py-1 bg-muted/50 rounded">
            <Calendar className="w-4 h-4 text-muted-foreground" />
            <span className="font-medium">Sep 12</span>
          </div>
          <Button variant="outline" size="icon" className="h-8 w-8">
            <ChevronRight className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8 ml-2">
            <Settings className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
};

export default FilterBar;
