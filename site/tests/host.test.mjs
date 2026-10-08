import test from 'node:test';
import assert from 'node:assert/strict';
import { shortHost } from '../src/lib/host.ts';

test('shortHost collapses Modal machine hostnames', () => {
  assert.equal(shortHost('k18karthikeya--verification-api.modal.run'), 'modal.run');
});

test('shortHost keeps localhost and simple labels untouched', () => {
  assert.equal(shortHost('127.0.0.1:8012'), '127.0.0.1:8012');
  assert.equal(shortHost('Same-origin proxy'), 'Same-origin proxy');
  assert.equal(shortHost('api.example.com'), 'api.example.com');
});
