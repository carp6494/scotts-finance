import { useEffect, useState } from 'react'
import { usePlaidLink } from 'react-plaid-link'
import { api } from '../api'

// Opens Plaid Link. With itemId it runs in update mode (reconnect a bank that needs login again).
export default function ConnectButton({ itemId, onDone, onError, label = 'Connect account', small = false }) {
  const [token, setToken] = useState(null)
  const [busy, setBusy] = useState(false)

  const { open, ready } = usePlaidLink({
    token,
    onSuccess: async (public_token, metadata) => {
      try {
        if (!itemId) {
          await api.exchange({
            public_token,
            institution_id: metadata?.institution?.institution_id,
            institution_name: metadata?.institution?.name,
          })
        } else {
          await api.sync()
        }
        onDone && onDone()
      } catch (e) {
        onError && onError(e.message)
      } finally {
        setBusy(false)
        setToken(null)
      }
    },
    onExit: () => { setBusy(false); setToken(null) },
  })

  useEffect(() => { if (token && ready) open() }, [token, ready, open])

  const start = async () => {
    setBusy(true)
    try {
      const r = await api.linkToken(itemId)
      setToken(r.link_token)
    } catch (e) {
      setBusy(false)
      onError && onError(e.message)
    }
  }

  return (
    <button type="button" className="press" onClick={start} disabled={busy}
      style={{
        height: small ? 32 : 40, padding: small ? '0 12px' : '0 16px', borderRadius: 8, border: 0,
        background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: small ? 12 : 13, opacity: busy ? 0.7 : 1,
      }}>
      {busy ? 'Opening...' : label}
    </button>
  )
}
