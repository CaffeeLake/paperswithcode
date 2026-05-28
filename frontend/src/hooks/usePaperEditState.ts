import { useState } from "react";

export function usePaperEditState() {
  const [isEditingTasks, setIsEditingTasks] = useState(false);
  const [isEditingMethods, setIsEditingMethods] = useState(false);
  const [isEditingRepositories, setIsEditingRepositories] = useState(false);
  const [isEditingProjectPages, setIsEditingProjectPages] = useState(false);
  const [isEditingEvaluations, setIsEditingEvaluations] = useState(false);
  const [isEditingSourceUrl, setIsEditingSourceUrl] = useState(false);

  return {
    // Tasks
    isEditingTasks,
    openTasksDialog: () => setIsEditingTasks(true),
    closeTasksDialog: () => setIsEditingTasks(false),
    setIsEditingTasks,

    // Methods
    isEditingMethods,
    openMethodsDialog: () => setIsEditingMethods(true),
    closeMethodsDialog: () => setIsEditingMethods(false),
    setIsEditingMethods,

    // Repositories
    isEditingRepositories,
    openRepositoriesDialog: () => setIsEditingRepositories(true),
    closeRepositoriesDialog: () => setIsEditingRepositories(false),
    setIsEditingRepositories,

    // Project pages
    isEditingProjectPages,
    openProjectPagesDialog: () => setIsEditingProjectPages(true),
    closeProjectPagesDialog: () => setIsEditingProjectPages(false),
    setIsEditingProjectPages,

    // Evaluations
    isEditingEvaluations,
    openEvaluationsDialog: () => setIsEditingEvaluations(true),
    closeEvaluationsDialog: () => setIsEditingEvaluations(false),
    setIsEditingEvaluations,

    // Source URL (external papers only)
    isEditingSourceUrl,
    openSourceUrlDialog: () => setIsEditingSourceUrl(true),
    closeSourceUrlDialog: () => setIsEditingSourceUrl(false),
    setIsEditingSourceUrl,
  };
}
