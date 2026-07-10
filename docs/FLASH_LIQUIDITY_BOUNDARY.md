# Flash-Liquidity Boundary

The term **flash liquidity** in this repository names a simulation variable and verification surface. It does not name an active borrowing capability.

The current code may:

- describe a provider;
- declare an available-capacity observation;
- construct amount buckets;
- calculate provider repayment;
- rank route/provider/bucket combinations;
- verify whether a modeled loop repays itself;
- emit review evidence with `authority: false`.

The current code may not:

- discover or use private keys;
- connect to a lending protocol;
- create, sign, or submit a transaction;
- request a real loan;
- mutate a mempool;
- schedule execution;
- move capital.

```text
Modeled liquidity is not borrowed liquidity.
Repayment evidence is not permission to borrow.
A profitable candidate is not an execution command.
```
