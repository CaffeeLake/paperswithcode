import React from "react";
import { useParams } from "react-router-dom";

import { OrganizationPaperFeed } from "@/components/OrganizationPaperFeed";
import NotFound from "@/pages/NotFound";

const OrganizationDetailView: React.FC = () => {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  return orgSlug ? <OrganizationPaperFeed organizationSlug={orgSlug} /> : <NotFound />;
};

export default OrganizationDetailView;
