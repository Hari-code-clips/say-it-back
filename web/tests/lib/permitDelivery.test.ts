import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Delivery, DeliveryTarget } from '../../src/api/types.ts'
import { permitDelivery } from '../../src/lib/permit.ts'

// SIB_OUTBOX (docs/EPERMIT_ADAPTER.md): the record says whether the permit system has the decision, never where it is.

const target = (kind: DeliveryTarget['kind'], status: DeliveryTarget['status']): DeliveryTarget => ({ kind, status, attempts: 1 })
const delivery = (...targets: DeliveryTarget[]): Delivery => ({ status: 'pending', targets })

describe('permitDelivery', () => {
  it('says sent when every permit system took it', () => {
    assert.equal(permitDelivery(delivery(target('permit', 'delivered'), target('chat', 'pending'))), 'delivered')
  })

  it('says retrying while any permit system is still pending, even if another failed', () => {
    assert.equal(permitDelivery(delivery(target('permit', 'failed'), target('permit', 'pending'))), 'retrying')
  })

  it('says not delivered when a permit system refused it or the tries ran out', () => {
    assert.equal(permitDelivery(delivery(target('permit', 'delivered'), target('permit', 'failed'))), 'notDelivered')
  })

  it('shows nothing without a permit system: Chat only, before a decision, or the outbox off', () => {
    assert.equal(permitDelivery(delivery(target('chat', 'failed'))), null)
    assert.equal(permitDelivery(null), null)
    assert.equal(permitDelivery(undefined), null)
  })
})
