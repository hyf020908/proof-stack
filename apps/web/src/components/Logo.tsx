import { Layers3 } from "lucide-react";
import { Link } from "react-router-dom";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" to="/" aria-label="ProofStack dashboard">
      <span className="brand__mark">
        <Layers3 size={20} strokeWidth={1.8} />
      </span>
      {!compact ? (
        <span>
          <strong>ProofStack</strong>
          <small>Evidence before merge</small>
        </span>
      ) : null}
    </Link>
  );
}
