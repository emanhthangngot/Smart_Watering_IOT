import { useContext } from "react";
import { OperationsContext, type OperationsValue } from "./operations-context";

export function useOperations(): OperationsValue {
  const value = useContext(OperationsContext);
  if (!value) throw new Error("useOperations must be used inside OperationsProvider");
  return value;
}
