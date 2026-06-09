import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

const PROFILE_PARAM = "profile_id";
const STORAGE_KEY = "taurus.selectedProfileId";

export function useSelectedProfileId() {
  const [searchParams, setSearchParams] = useSearchParams();
  const profileFromUrl = searchParams.get(PROFILE_PARAM)?.trim() || "";
  const [storedProfileId, setStoredProfileId] = useState(readStoredProfileId);
  const selectedProfileId = profileFromUrl || storedProfileId || undefined;

  useEffect(() => {
    if (!profileFromUrl) {
      return;
    }
    setStoredProfileId(profileFromUrl);
    writeStoredProfileId(profileFromUrl);
  }, [profileFromUrl]);

  const setSelectedProfileId = useCallback(
    (profileId: string) => {
      const normalized = profileId.trim();
      if (!normalized) {
        return;
      }
      setStoredProfileId(normalized);
      writeStoredProfileId(normalized);
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.set(PROFILE_PARAM, normalized);
          return next;
        },
        { replace: false },
      );
    },
    [setSearchParams],
  );

  return { selectedProfileId, setSelectedProfileId };
}

export function useProfilePath() {
  const { selectedProfileId } = useSelectedProfileId();
  return useCallback(
    (path: string) => withProfilePath(path, selectedProfileId),
    [selectedProfileId],
  );
}

export function withProfilePath(path: string, profileId: string | null | undefined): string {
  if (!profileId) {
    return path;
  }
  const [pathname, search = ""] = path.split("?");
  const params = new URLSearchParams(search);
  params.set(PROFILE_PARAM, profileId);
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function readStoredProfileId(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY)?.trim() || "";
  } catch {
    return "";
  }
}

function writeStoredProfileId(profileId: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, profileId);
  } catch {
    // Local storage can be unavailable in restricted browser contexts.
  }
}
