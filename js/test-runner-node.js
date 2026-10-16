import test from "node:test";
import { tests } from "./test.js";

for (const item of tests) {
  test(item.name, async () => {
    await item.run();
  });
}
