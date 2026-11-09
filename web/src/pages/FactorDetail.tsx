import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { factorHref } from "../factorName";

/** Legacy `/factor/:name` links: open the base factor's home page with that version selected. */
export default function FactorDetail() {
  const name = useParams().name ?? "";
  const [params] = useSearchParams();
  return <Navigate replace to={factorHref(name, { period: params.get("period") })} />;
}
