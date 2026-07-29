import React from "react";
import { useParams } from "react-router-dom";

import { OrganizationPaperFeed } from "@/components/OrganizationPaperFeed";
import NotFound from "@/pages/NotFound";

const OrganizationTaskView: React.FC = () => {
  const { orgSlug, taskSlug } = useParams<{
    orgSlug: string;
    taskSlug: string;
  }>();
  return orgSlug && taskSlug ? (
    <OrganizationPaperFeed
      organizationSlug={orgSlug}
      taskSlug={taskSlug}
    />
  ) : (
    <NotFound />
  );
};

export default OrganizationTaskView;
