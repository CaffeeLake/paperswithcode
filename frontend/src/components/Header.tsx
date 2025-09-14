import { Search, Sparkles, Menu, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Link, useLocation } from "react-router-dom";

const Header = () => {
  const location = useLocation();
  
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 shadow-header">
      <div className="container mx-auto px-4">
        <div className="flex h-16 items-center justify-between">
          {/* Logo and Navigation */}
          <div className="flex items-center space-x-8">
            <Link to="/" className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-gradient-primary rounded-lg flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <span className="text-xl font-semibold">AI Papers</span>
            </Link>
            
            <nav className="hidden md:flex items-center space-x-6">
              <Link to="/">
                <Button 
                  variant="ghost" 
                  className={`text-sm font-medium ${
                    location.pathname === '/' ? 'text-primary' : ''
                  }`}
                >
                  Papers
                </Button>
              </Link>
              <Link to="/tasks">
                <Button 
                  variant="ghost" 
                  className={`text-sm font-medium ${
                    location.pathname === '/tasks' ? 'text-primary' : ''
                  }`}
                >
                  Tasks
                </Button>
              </Link>
              <Link to="/methods">
                <Button 
                  variant="ghost" 
                  className={`text-sm font-medium ${
                    location.pathname === '/methods' ? 'text-primary' : ''
                  }`}
                >
                  Methods
                </Button>
              </Link>
            </nav>
          </div>

          {/* Search Bar */}
          <div className="flex-1 max-w-md mx-8">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <Input
                className="pl-10 bg-muted/50 border-0 focus-visible:ring-1 focus-visible:ring-primary"
                placeholder="Search papers, authors, tasks..."
              />
            </div>
          </div>

          {/* User Actions */}
          <div className="flex items-center space-x-4">
            <Button variant="outline" size="sm">
              + Submit a paper
            </Button>
            <Avatar className="w-8 h-8">
              <AvatarImage src="/placeholder-avatar.jpg" />
              <AvatarFallback>
                <User className="w-4 h-4" />
              </AvatarFallback>
            </Avatar>
            <Button variant="ghost" size="icon" className="md:hidden">
              <Menu className="w-5 h-5" />
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;