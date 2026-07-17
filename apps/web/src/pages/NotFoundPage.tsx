import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, EmptyState } from "../components/ui";

export function NotFoundPage() {
  return (
    <div className="not-found">
      <EmptyState
        icon={<Compass />}
        title="This evidence trail ends here"
        description="The page may have moved, or your organization does not have access to it."
        action={
          <Link to="/">
            <Button>Return to overview</Button>
          </Link>
        }
      />
    </div>
  );
}
