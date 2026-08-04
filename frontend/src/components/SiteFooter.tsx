import { Link, useLocation } from "react-router-dom";

const SiteFooter = () => {
  const { pathname } = useLocation();

  if (pathname === "/chat" || pathname.startsWith("/chat/")) return null;

  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <span>© {new Date().getFullYear()} Hugging Face</span>
        <Link to="/privacy">Privacy</Link>
        <a
          href="https://github.com/huggingface/paperswithcode-feedback/issues"
          target="_blank"
          rel="noreferrer"
        >
          Feedback
        </a>
      </div>
    </footer>
  );
};

export default SiteFooter;
