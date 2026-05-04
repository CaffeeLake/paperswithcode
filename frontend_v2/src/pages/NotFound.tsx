import { Link, useLocation } from "react-router-dom";
import { useEffect } from "react";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="page" style={{ textAlign: "center", paddingTop: 96 }}>
      <h1 className="detail-title" style={{ fontSize: 96, marginBottom: 8 }}>
        404
      </h1>
      <p style={{ fontFamily: "var(--serif)", fontStyle: "italic", color: "var(--ink-soft)", marginBottom: 24 }}>
        That route isn't on the map.
      </p>
      <Link to="/" className="action-btn">
        Return home
      </Link>
    </div>
  );
};

export default NotFound;
