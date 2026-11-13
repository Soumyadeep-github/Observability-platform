// Copyright contributors to the Marquez project. SPDX-License-Identifier: Apache-2.0
// Vendored from Marquez 0.50.0 (4984ca939b3a6f59e1092c6397702eb1e53ff1cc). See NOTICE.md.
import { useCallback, useEffect, useRef } from 'react'

export function useCallbackRef<T extends (...args: any[]) => any>(
  callback: T | undefined,
  deps: React.DependencyList = []
) {
  const callbackRef = useRef(callback)

  useEffect(() => {
    callbackRef.current = callback
  })

  return useCallback(((...args) => callbackRef.current?.(...args)) as T, deps)
}
